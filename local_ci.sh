#!/usr/bin/env bash
set -euo pipefail

# -----------------------
# Configuration (override via env vars)
# -----------------------
SRC_DIR="${SRC_DIR:-src/pytribeam}"

# tests: simulator | hardware | none
TEST_MODE="${TEST_MODE:-simulator}"

# combine simulator/hardware .coverage into combined/
COMBINE_COVERAGE="${COMBINE_COVERAGE:-0}"

# coverage badge source: simulator | hardware | combined
BADGE_FROM="${BADGE_FROM:-simulator}"

# if TEST_MODE=hardware, stop on first failure
HARDWARE_STOP_ON_FAIL="${HARDWARE_STOP_ON_FAIL:-1}"

# Exclude regex for docstr-coverage (matches your markdown)
DOCSTR_EXCLUDE_RE="${DOCSTR_EXCLUDE_RE:-.*(GUI)}"

# -----------------------
# Helpers
# -----------------------
need() { command -v "$1" >/dev/null 2>&1 || { echo "ERROR: Missing command: $1" >&2; exit 1; }; }

badge_color() {
  awk -v coverage="$1" 'BEGIN {
    if (coverage < 40) print "red";
    else if (coverage < 80) print "orange";
    else if (coverage < 90) print "yellow";
    else print "green";
  }'
}

# -----------------------
# Checks
# -----------------------
need git bash 2>/dev/null || true   # not required; just avoids confusion if people expect git-bash env
need curl
need mdbook
need pdoc
need interrogate
need anybadge
need pytest
need coverage
need pylint
need pylint-exit
need awk
need sed
need grep
need tee

[[ -f pyproject.toml || -f README.md ]] || {
  echo "ERROR: Run from repo root (expected pyproject.toml and/or README.md)." >&2
  exit 1
}

mkdir -p badges logs coverage_reports/{simulator,hardware,combined} docs/api

echo "=== Local CI workflow (no git actions) ==="
echo "TEST_MODE=$TEST_MODE  COMBINE_COVERAGE=$COMBINE_COVERAGE  BADGE_FROM=$BADGE_FROM"
echo

# -----------------------
# userguide (mdbook)
# -----------------------
echo "=== Build userguide (mdbook) ==="
mdbook build .

echo "=== userguide badge ==="
curl -k -L -o badges/userguide.svg \
  "https://img.shields.io/badge/userguide-Book-blue?logo=mdbook&logoColor=FFFFFF"

# -----------------------
# API docs + docstring badge
# -----------------------
echo
echo "=== Docstring coverage badge ==="

# -v prints a table including a TOTAL row with the percentage.
# --fail-under 0 prevents interrogate from exiting nonzero due to coverage %.
INTERROGATE_OUT="$(interrogate -v --fail-under 0 src 2>&1)"

# Parse the numeric percent from the TOTAL row.
# Example TOTAL row ends with something like: "87.5"
DOCSTRING_COVERAGE="$(
  printf "%s\n" "$INTERROGATE_OUT" \
  | awk '/^TOTAL[[:space:]]/ {print $NF; exit}'
)"

if [[ -z "${DOCSTRING_COVERAGE}" ]]; then
  echo "WARNING: Could not parse interrogate TOTAL coverage. Output was:"
  echo "$INTERROGATE_OUT"
else
  # Normalize to one decimal place (handles "87" or "87.5")
  DOCSTRING_COVERAGE="$(awk -v x="$DOCSTRING_COVERAGE" 'BEGIN{printf "%.1f", x}')"
  API_COLOR="$(badge_color "$DOCSTRING_COVERAGE")"
  anybadge -o -l api -v "${DOCSTRING_COVERAGE}% coverage" -f badges/api.svg -c "$API_COLOR"
  echo "Docstring coverage: ${DOCSTRING_COVERAGE}% ($API_COLOR)"
fi

# -----------------------
# Tests + coverage
# -----------------------
echo
echo "=== Tests + coverage ==="
PYTEST_RC=0

case "$TEST_MODE" in
  simulator)
    set +e
    pytest --cov=pytribeam \
      --cov-report=html:coverage_reports/simulator/htmlcov/ \
      --cov-report=xml:coverage_reports/simulator/coverage.xml \
      --cov-report term-missing
    PYTEST_RC=$?
    set -e
    [[ -f .coverage ]] && mv -f .coverage coverage_reports/simulator/.coverage
    ;;
  hardware)
    STOPFLAG=""
    [[ "$HARDWARE_STOP_ON_FAIL" == "1" ]] && STOPFLAG="-x"
    set +e
    pytest $STOPFLAG --cov=pytribeam \
      --cov-report=html:coverage_reports/hardware/htmlcov/ \
      --cov-report=xml:coverage_reports/hardware/coverage.xml \
      --cov-report term-missing
    PYTEST_RC=$?
    set -e
    [[ -f .coverage ]] && mv -f .coverage coverage_reports/hardware/.coverage
    ;;
  none)
    echo "Skipping tests."
    ;;
esac

if [[ "$PYTEST_RC" != "0" ]]; then
  echo "WARNING: pytest failed (exit code $PYTEST_RC). Continuing workflow..."
fi

# -----------------------
# Combine coverage (optional)
# -----------------------
if [[ "$COMBINE_COVERAGE" == "1" ]]; then
  echo
  echo "=== Combine coverage (if inputs exist) ==="
  sim="coverage_reports/simulator/.coverage"
  hw="coverage_reports/hardware/.coverage"

  if [[ -f "$sim" || -f "$hw" ]]; then
    rm -f .coverage
    args=()
    [[ -f "$sim" ]] && args+=("$sim")
    [[ -f "$hw"  ]] && args+=("$hw")

    coverage combine --append --keep "${args[@]}"
    coverage html -d coverage_reports/combined/htmlcov
    coverage xml -o coverage_reports/combined/coverage.xml
  else
    echo "No .coverage files found; skipping combine."
  fi
fi

# -----------------------
# Coverage badge
# -----------------------
echo
echo "=== Test coverage badge ==="
XML="coverage_reports/${BADGE_FROM}/coverage.xml"
if [[ ! -f "$XML" ]]; then
  echo "WARNING: Coverage XML not found: $XML (skipping coverage badge)"
else
  LINES_COVERED="$(grep -oP 'lines-covered="\K[0-9]+' "$XML" || true)"
  LINES_VALID="$(grep -oP 'lines-valid="\K[0-9]+' "$XML" || true)"

  if [[ -n "$LINES_COVERED" && -n "$LINES_VALID" && "$LINES_VALID" -ne 0 ]]; then
    COVERAGE_PERCENTAGE="$(awk "BEGIN {printf \"%.1f\", (${LINES_COVERED}/${LINES_VALID})*100}")"
    COV_COLOR="$(badge_color "$COVERAGE_PERCENTAGE")"
    anybadge -o -l "Coverage" -v "${COVERAGE_PERCENTAGE}%" -f badges/test-coverage.svg -c "$COV_COLOR"
    echo "Coverage: ${COVERAGE_PERCENTAGE}% ($COV_COLOR)"
  else
    echo "WARNING: Could not parse coverage totals from $XML"
  fi
fi

# -----------------------
# Lint + lint badge
# -----------------------
echo
echo "=== pylint + lint badge ==="
pylint -v "$SRC_DIR" | tee logs/lint.log || pylint-exit $?

PYLINT_SCORE="$(sed -n 's/^Your code has been rated at \([-0-9.]*\)\/.*/\1/p' logs/lint.log | tail -n 1 || true)"
if [[ -n "$PYLINT_SCORE" ]]; then
  anybadge -o --label=lint --file=badges/lint.svg --value="${PYLINT_SCORE}" 2=red 4=orange 8=yellow 10=green
  echo "pylint score: $PYLINT_SCORE"
else
  echo "WARNING: Could not parse pylint score; skipping lint badge"
fi

echo
echo "Done. Artifacts updated in: badges/, logs/, docs/, coverage_reports/"
