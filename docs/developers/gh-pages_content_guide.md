As autoscript requires a license, content for GitHub pages must be generated locally on a licensed machine. This file contains instructions and commands to create content for github pages for the gh-pages branch.

# overwriting gh-pages

In order to manually overwrite the content of gh-pages, you should start from an up-to-date version of the "main" branch:

```sh
git switch main
git pull
```

From here you can checkout and reset the gh-pages branch:

```sh
git checkout -B gh-pages
```

Now build the various pages by following the sections below:

- [userguide](#userguide)
- [api-docs](#api-docs)
- [test_coverage](#test-coverage)
- [linting](#lint-logs)
- [versioning](#versioning)

Once all the new build content is added, modify the top of the .gitignore file by changing the top lines from this:
```
# gh-pages stuff (need to build locally from main)
badges/
coverage_reports/
logs/
docs/api/
docs/userguide/book/
```

to this:
```txt
# # gh-pages stuff (need to build locally from main)
# badges/
# coverage_reports/
# logs/
# docs/api/
# docs/userguide/book/
```

Now stage all changes and commit to the gh-pages branch:
```sh
git add .
git commit -m "Update gh-pages branch to reflect current main branch"
```

And finally push your commit:
```sh
git push -f origin gh-pages
```


## userguide

The userguide is built with mdbooks, a rust crate, so the local machine must have a version of rust installed with the following crates installed:
- mdbook
- mdbook-cmdrun
- mdbook-katex

From the root directory of the repo (directory containing README.md, pyproject.toml, book.toml, etc.) a developer can use the following commands to perform various actions related to the userguide.

The userguide can be edited in place as follows:
```sh
mdbook serve . --open
```

The userguide can be built with the following:
```sh
mdbook build .
```

The userguide badge can be created as follows, but this should only need to be done once:
```sh
# insecure curl (-k option)
curl -k -L -o badges/userguide.svg "https://img.shields.io/badge/userguide-Book-blue?logo=mdbook&logoColor=FFFFFF"
```

## api docs

Run the following in a git bash terminal on Windows:

```sh
pdoc ./src/pytribeam/  -o ./docs/api
test -d badges/ || mkdir -p badges
# anybadge -o -l api -v passing -f badges/api.svg -c green
#docstring coverage
DOCSTRING_COVERAGE_RAW=$(docstr-coverage --percentage-only src/ -e ".*(GUI)")
DOCSTRING_COVERAGE=$(printf "%.1f" "$DOCSTRING_COVERAGE_RAW")
echo "Coverage Percentage: $DOCSTRING_COVERAGE%"
# Determine badge color based on coverage percentage using awk for comparison
COLOR=$(awk -v coverage="$DOCSTRING_COVERAGE" 'BEGIN {
    if (coverage < 40) {
        print "red"
    } else if (coverage < 80) {
        print "orange"
    } else if (coverage < 90) {
        print "yellow"
    } else {
        print "green"
    }
}')
echo "badge color: $COLOR"
anybadge -o -l api -v "$DOCSTRING_COVERAGE% coverage" -f badges/api.svg -c "$COLOR"
```

## test coverage

In order to run tests, the user must install ``pyTriBeam`` in editable mode and add their computer name to the list of machines in the ``Constants`` module. To find your hardware name, you can run the following from a python terminal:

```python
import platform
print(platform.node())
```

### How to run test suite on simulator:
Go to the root directory of `pytribeam` and run the following in a git bash terminal window. This will generate both a .xml and .html version of the coverage report.
```sh
pytest --cov=pytribeam --cov-report=html:coverage_reports/simulator/htmlcov/ --cov-report=xml:coverage_reports/simulator/coverage.xml --cov-report term-missing
```
A `.coverage` file will be generated in the root directory of `pytribeam`. Move the `.coverage` file into the `coverage_reports/simulator` folder.

### How to run test suite on hardware:
The microscope must first be prepared in order to safely run all tests. It is highly recommended to remove any sample and sample holder from the tool. **DO NOT run hardware tests if you are unfamiliar with the process.**

Prepare the microscope by doing the following:

- Remove CBS stage restrictions (non-Windows 7 machines)
- Turn on electron beam, focus and link Z
- For laser systems only:
    - Open laser app and disable laser interlock (turn the key so laser can fire)
    - Open EBSD software, enable proximity sensor and override alerts (Oxford only)

From the root directory of `pytribeam`, run the following from command from a terminal, this will generate both a .xml and .html version of test coverage:
```sh
pytest --cov=pytribeam --cov-report=html:coverage_reports/hardware/htmlcov/ --cov-report=xml:coverage_reports/hardware/coverage.xml --cov-report term-missing
```

A `.coverage` file will be generated in the root directory of `pytribeam`. Move the `.coverage` file into the `coverage_reports/hardware` folder.

### Combine test coverage

Combining test coverage reports allows us to account for differences in coverage for tests that can only run on specific hardware versions (e.g. systems with a laser) or that can run on a simulated microscope environment. When combining coverage reports, it is assumed to be performed on a non-microscope machine with an internet connection (with an `Offline` autoscript install). In order to combine coverage reports, the `.coveragerc` file must include the paths to all `pytribeam/src` directories used to generate `.coverage` files. A working example from 2/18/26 is given below:

`.coveragerc`:
```
[run]
omit =
    # omit GUI files from tests
    src/pytribeam/GUI/*

[paths]
    source = 
        src/ # running from pytribeam root on an offline machine
        C:/Users/User/Desktop/Polonsky/____SOFTWARE/pytribeam/src # full path to 'pytribeam/src' on a laser system
        C:/Users/User/Documents/pytribeam/src # full path to `pytribeam/src` on a different laser system

```


Combine coverage reports using the generated `.coverage` files:

```sh
coverage combine --append --keep ./coverage_reports/simulator/.coverage ./coverage_reports/hardware/.coverage
```

Then generate a html report from the combined `.coverage` file, which should appear in the root directory of `pytribeam`:

```sh
coverage html -d ./coverage_reports/combined/htmlcov
```

Alternatively (or additionally), an .xml report can be generated from the combined `.coverage` file:

```sh
coverage xml -o ./coverage_reports/combined/coverage.xml
```

Now make badge in git-bash terminal:

```sh
pip install anybadge # if needed, should already be installed in local environment
test -d badges/ || mkdir -p badges/
LINES_COVERED=$(grep -oP 'lines-covered="\K[0-9]+' coverage_reports/combined/coverage.xml)
LINES_VALID=$(grep -oP 'lines-valid="\K[0-9]+' coverage_reports/combined/coverage.xml)
if [ "$LINES_VALID" -ne 0 ]; then \
    COVERAGE_PERCENTAGE=$(awk "BEGIN {printf \"%.1f\", ($LINES_COVERED / $LINES_VALID) * 100}"); \
    COLOR=$(awk -v coverage="$COVERAGE_PERCENTAGE" 'BEGIN { \
        if (coverage < 40) { print "red" } \
        else if (coverage < 80) { print "orange" } \
        else if (coverage < 90) { print "yellow" } \
        else { print "green" } \
    }'); \
    anybadge -o -l "Coverage" -v "$COVERAGE_PERCENTAGE%" -f badges/test-coverage.svg -c "$COLOR"; \
else \
    echo "Lines Valid is zero, cannot calculate coverage percentage."; \
fi
```

## lint logs

To generate a lint.log file and badge for lint score, run the following commands in a git bash terminal: 

```sh
mkdir -p logs/

# optionally ignore GUI for linting
# pylint -v --ignore=GUI src/pytribeam | tee logs/lint.log || pylint-exit $?

pylint -v src/pytribeam | tee logs/lint.log || pylint-exit $?

test -d badges/ || mkdir -p badges/
PYLINT_SCORE=$(sed -n 's/^Your code has been rated at \([-0-9.]*\)\/.*/\1/p' logs/lint.log)
anybadge -o --label=lint --file=badges/lint.svg --value=${PYLINT_SCORE} 2=red 4=orange 8=yellow 10=green
```

## versioning

Notes to come