# Contributing

## Repository Download

```sh
git clone git@github.com:sandialabs/pytribeam.git
```

## Virtual Environment

From within the `pytribeam` directory, create a virtual environment.  A virtual environment is a self-contained directory that contains a specific Python installation, along with additional packages. It allows users to create isolated environments for different projects. This ensures that dependencies and libraries do not interfere with each other.

Create a virtual environment with either `pip` or `uv`.  `pip` is already included with Python.  `uv` must be [installed](https://docs.astral.sh/uv/getting-started/installation/).  `uv` is 10 to 100 times faster than `pip`.

```sh
cd pytribeam

# (a) pip method, or
python -m venv .venv

# (b) uv method
uv venv

# for both methods (a) and (b)
source .venv/bin/activate       # bash
source .venv/bin/activate.fish  # fish shell
```

Install the code in editable form,

```sh
# (a) pip method, or
pip install -e .[dev]

# (b) uv method
uv pip install -e .[dev]
```

## CI/CD

We separate the concerns of test, build, release, and publish throughout the `.github/workflows/` files:

* [`ci.yml`](/.github/workflows/ci.yml) — runs on every push to any branch
* [`release.yml`](/.github/workflows/release.yml) — runs on version tag pushes (`v*`)
* [`publish-docs-image.yml`](/.github/workflows/publish-docs-image.yml) — manually triggered to rebuild the docs builder Docker image

These YAML files cover:

* Continuous Integration (CI)
  * **Validate Tag**
    * **Purpose:** To catch mistakes before anything is built or published. Only runs in `release.yml` on tag pushes.
    * **What happens:** Three checks run in sequence: (1) the tag must be on `main` or `dev` (not a feature branch); (2) the tag must conform to PEP 440 (e.g., `v1.0.0`, `v1.0.0rc1`); (3) the tag must be strictly newer than all existing tags.
    * **Key Outcome:** Safety. A mistyped version or a tag on the wrong branch is caught immediately, before any build artifacts are produced.
  * **Test (Verification)**
    * **Purpose:** To ensure that the code is functional and hasn't introduced regressions (broken existing features).
    * **What happens:** Automated tools like `pytest` run your unit and integration tests. It often includes "linting" (checking code style) and type-checking.
    * **Key Outcome:** Confidence. If this stage fails, the process stops immediately, preventing broken code from ever reaching a user.
  * **GitHub Pages (Documentation Deploy)**
    * **Purpose:** To keep the published documentation in sync with the latest code on `dev` and `main`.
    * **What happens:** After tests pass, `ci.yml` builds the user guide with `mdbook`, generates badges and HTML reports, and deploys them to the `gh-pages` branch under a `dev/` or `main/` subdirectory so both coexist.
    * **Key Outcome:** Up-to-date documentation is always available for both the development and released versions of the project.
  * **Build (Packaging)**
    * **Purpose:** To transform your "human-readable" source code into "machine-installable" artifacts. This is the bridge between CI and CD. Once the code is verified (integrated), it can be packaged into a deployable format (Wheels/SDists).
    * **What happens:** Tools (like `uv build`) bundle your code into standard formats, such as a Wheel (`.whl`) or a Source Distribution (`.tar.gz`).
    * **Key Outcome:** Portability. You now have a single file (an "artifact") that contains everything needed to install your library on any compatible system.
  * **Release (Documentation & Tagging)**
    * **Purpose:** To create an official "point-in-time" snapshot of the project for project management and users. It uses an immutable Git tag and GitHub Release page.
    * **What happens:** A permanent Git tag (like v1.0.0) is assigned to a specific commit. A GitHub Release page is generated with a Changelog (i.e., What's New?) and the build artifacts are attached to it as "Release Assets."
    * **Key Outcome:** Traceability. It provides a clear history of the project's evolution and a stable place for users to download specific versions.
* Continuous Delivery (CD)
  * **Publish (Distribution)**
    * **Purpose:** To make the software easily available to the global ecosystem.
    * **What happens:** The built artifacts are uploaded to a package registry, such as PyPI (the Python Package Index).
    * **Key Outcome:** Accessibility. Once published, anyone in the world can install your software using a simple command like `pip install pytribeam`.

Implementation details:

* The reuse of `ci.yml` via a `workflow_call` in `release.yml` ensures that test logic is not duplicated.
* **Dependency Chain:** `test` waits for `validate_tag`; `build` waits for `test`; `github-release` waits for `build`; `publish` waits for both `build` and `github-release`.
* **No commit-back of `_version.py`:** `hatch-vcs` stamps the exact version into the built wheel/sdist from the git tag, so published artifacts are always correct. The workflow does **not** regenerate and commit `_version.py` back to `main`/`dev` — doing so would create a commit *past* the tag (forcing every later build to report the next `.devN` version) and would fail against branch protection on `main`. Commit traceability is preserved by the tag itself (see [Tags and Semantic Versioning](#tags-and-semantic-versioning)).
* **Artifact Integrity:** By building once and downloading the artifacts in subsequent jobs, we ensure the exact same files go to GitHub and PyPI.
* **Security:** We use `id-token: write` for PyPI's Trusted Publishing, which is a modern and secure way to handle authentication.

## Trusted Publishing

In `release.yml` we have removed the manual `-p ${{ secrets.PYPI_TOKEN }}`. The industry standard is now [**Trusted Publishing**](https://docs.pypi.org/trusted-publishers/) (also called OpenID Connect or OIDC). You configure this in your PyPI project settings once, and GitHub Actions authenticates securely without you needing to store and rotate secrets.

> OpenID Connect (OIDC) provides a flexible, credential-free mechanism for delegating publishing authority for a PyPI package to a trusted third party service, like GitHub Actions. PyPI users and projects can use trusted publishers to automate their release processes, without needing to use API tokens or passwords.

To configure Trusted Publishing, you tell PyPI, "Trust any code from this specific GitHub repository and workflow." This removes the need to manage long-lived API tokens or passwords in your secrets.

**Step 1 — Set the environment in `release.yml`**

The environment must be set to either `pypi` or `testpypi` depending on the version string. Hence the logic in `release.yml`:

```yaml
environment: ${{ (contains(github.ref, 'rc') || contains(github.ref, 'dev')) && 'testpypi' || 'pypi' }}
```

Tags containing `rc` or `dev` (e.g., `v0.0.9rc1`, `v1.0.0.dev1`) route to TestPyPI. All other tags route to production PyPI. The `repository-url` in the publish step is set conditionally by the same logic.

**Step 2 — Create the GitHub environments**

The GitHub repository itself must have both a `pypi` and a `testpypi` environment:

* Click on the **Settings** tab (usually the last tab on the right in the top navigation bar).
* On the left-hand sidebar, look for the **Environments** link (it's under the "Code and automation" section).
  * If the environment doesn't exist yet:
    * Click the **New environment** button.
    * Name the environment `pypi` (and then make a second item called `testpypi`) and click **Configure environment**.
  * If it does exist but is named differently, you can click on it to rename it or delete it and create a new one.
* For a basic setup using Trusted Publishing, you don't actually need to add any secrets or configuration on this page. Just having the environment named `testpypi` exist is enough to link it to your workflow.
* Optionally, add the following protections:
  * Under **Deployment branches and tags**, under the **No Restriction** button, select **Selected branches and tags**.
  * Click **Add deployment branch or tag rule**.
  * Select **Ref type: Tag**.
  * Set the **Name Pattern** to `v*`. This ensures that *only* version tags can ever use this environment, adding a layer of security.

**Step 3 — Configure the PyPI (or TestPyPI) publisher**

* Log into your [PyPI](https://pypi.org) (or [Test PyPI](https://test.pypi.org)) account.
* Go to your project's **Manage** page (or your account's **Publishing** settings if you are setting it up for the first time).
* Look for the **Publishing** tab.
* Click **Add new publisher**.
* Select **GitHub** as the source.
* Enter the following details:
  * **Owner:** `sandialabs`
  * **Repository name:** `pytribeam`
  * **Workflow name:** `release.yml` (this must match the filename in your `.github/workflows/` directory)
  * **Environment name:** `pypi` for live publishing to PyPI, or `testpypi` for test publishing to TestPyPI.
* Click the **Add** button.

## Tags and Semantic Versioning

We follow [PEP 440](https://peps.python.org/pep-0440/) (the Python standard for versioning), which requires version strings to follow this specific structure:

```
N.N.N[{a|b|rc}N][.postN][.devN]
```

The `validate_tag` job in `release.yml` enforces that a tag can be added only when the branch is `main` or `dev`, that the tag follows PEP 440, and that the version is strictly newer than all existing tags.

Version strings are generated automatically by `hatch-vcs` (which uses `setuptools-scm` under the hood) via `git describe --tags`. For example, a version of `0.0.9.dev173` means:

* `0.0.9` — the most recent git tag
* `dev173` — 173 commits have been made since that tag

Each new commit increments the distance by 1. When a commit is tagged (e.g., `v0.1.0`), the distance resets to zero and the version becomes the clean `0.1.0` with no `.dev` suffix. This clean version is written to `src/pytribeam/_version.py` **at build time** and baked into the wheel and sdist, so everything published to PyPI/TestPyPI reports the correct version.

**The tag is the permanent link between a version and a commit.** A git tag is an immutable pointer to exactly one commit, so the three are locked together one-to-one:

```
published version string   ⇄   tag name   ⇄   commit SHA (immutable)
       "0.1.1"                   v0.1.1         3b3dd19...
```

Because every published artifact is built from a tag, the version string alone identifies the commit — no commit hash needs to be embedded in `_version.py`:

```sh
# "I installed 0.1.1 from PyPI — which commit is that?"
git rev-list -n1 v0.1.1     # -> the exact commit SHA, every time
```

The GitHub Release page for each tag links the same commit directly, and `git describe --tags` gives developers the nearest tag, commits-since, and short hash for local (unpublished) builds. For this reason `release.yml` does **not** commit a regenerated `_version.py` back to `main`/`dev`: the tracked `src/pytribeam/_version.py` is only a static fallback for source-zip downloads, while the tag provides authoritative traceability.

**Pre-release tags:**

| Tag | Description |
|---|---|
| `v1.1.0a1` | The first alpha for version 1.1.0 |
| `v1.1.0b2` | The second beta for version 1.1.0 |
| `v1.1.0rc1` | The first release candidate for version 1.1.0 |

A release candidate is made during the final testing stage before a full release.

**Stable release tags** (e.g., starting from the `v1.0.0` release):

| Tag | Description |
|---|---|
| `v1.0.1` | Patch release: backwards-compatible bug fixes |
| `v1.1.0` | Minor release: new features that are backwards-compatible |
| `v2.0.0` | Major release: significant changes or breaking API updates |

**Development and post-release tags:**

| Tag | Description |
|---|---|
| `v1.1.0.dev1` | A version currently under development |
| `v1.0.0.post1` | Fixes a minor error in the release process (e.g., a documentation typo) without changing the code |

## Manual Release

### Understanding the Tag Validation Race Condition

The `release.yml` workflow includes a `validate_tag` job that checks whether a tag is reachable from `origin/main` or `origin/dev`. This validation uses:

```bash
git branch -r --contains refs/tags/v1.0.0rc1
```

This command returns which remote branches contain the commit that the tag points to. The validation **fails** if the tag points to a commit that doesn't exist on the remote branch yet.

**How the race condition occurs:**

1. You create tag `v1.0.0rc1` locally on commit `abc123`
2. You run `git push origin v1.0.0rc1` (pushes only the tag)
3. Commit `abc123` has NOT been pushed to `origin/dev` yet
4. GitHub receives the tag but when CI runs validation:
   - It checks: "Is commit `abc123` on `origin/dev`?"
   - Answer: No (the commit was never pushed to the branch)
   - Result: Validation fails with "Tag must be created on 'main' or 'dev' branch"

**Why it happens:**
- Tags and commits are separate refs in git
- Pushing a tag does NOT automatically push the commits it points to
- If the branch tip hasn't been pushed, the commit behind the tag won't exist on the remote yet

**Prevention:**
Always push your branch commits FIRST, then push the tag. This ensures the commit exists on the remote before the tag references it.

**Correct push order:**
```bash
git push origin dev        # Push the branch (includes all commits)
git push origin v1.0.0rc1  # Push the tag (now it points to an existing remote commit)
```

**Incorrect push order (causes race condition):**
```bash
git push origin v1.0.0rc1  # Push tag first
git push origin dev        # Push branch second (too late — CI already validated)
```

### Pre-flight Check

Before creating any release, run the preflight script to verify your repository state:

```sh
python preflight.py --release
```

This will verify:
- You are on the correct branch (`main` or `dev`)
- All local commits are pushed to the remote
- No unpushed changes remain
- The repository is ready for tagging

### Create a Pre-release (TestPyPI from `dev`)

Use this path to validate the full release pipeline — build, attestation, GitHub Release, and publish — without touching the production package index. Tags containing `rc` or `dev` are automatically routed to TestPyPI by `release.yml`.

```sh
# Ensure you are on the dev branch and up to date
git checkout dev
git pull

# View existing tags to choose the next version
git tag

# Push any branch commits to remote FIRST (prevents the tag-validation race
# condition described above). There is nothing to build or commit locally:
# hatch-vcs generates _version.py with the correct version during the CI build.
git push origin dev

# Create a release candidate tag (rc) — this routes to TestPyPI
git tag -a v1.0.0rc1 -m "Release candidate 1 for version 1.0.0"

# Push the tag to GitHub — this triggers release.yml
# The tag now points to a commit already on origin/dev, so CI validation will succeed
git push origin v1.0.0rc1
```

After pushing, `release.yml` will:
1. Validate the tag (branch, PEP 440, version ordering)
2. Run the full test suite
3. Build the wheel and sdist with SLSA attestation (version stamped from the tag)
4. Create a GitHub Release marked as **pre-release**
5. Publish to **TestPyPI** (because the tag contains `rc`)

Verify the TestPyPI release at `https://test.pypi.org/project/pytribeam/` and test install with:

```sh
pip install --index-url https://test.pypi.org/simple/ pytribeam==1.0.0rc1
```

### Create a Release (PyPI from `main`)

Once the pre-release is validated, merge `dev` into `main` and tag a production release. Tags without `rc` or `dev` are routed to production PyPI.

**Pre-flight check:** Run `python preflight.py --release` before proceeding.

```sh
# Merge dev into main
git checkout main
git pull origin main
git merge dev
git push origin main

# View existing tags to confirm the next version
git tag

# Push main to remote FIRST (prevents the tag-validation race condition).
# Nothing to build or commit locally — hatch-vcs stamps the version during CI.
git push origin main

# Create the production release tag — this routes to PyPI
git tag -a v1.0.0 -m "Release version 1.0.0"

# Push the tag to GitHub — this triggers release.yml
# The tag now points to a commit already on origin/main, so CI validation will succeed
git push origin v1.0.0
```

After pushing, `release.yml` will run the same pipeline as above but create a **full release** on GitHub and publish to **production PyPI**. If the manual approval gate is configured on the `pypi` environment, the `publish` job will pause for reviewer sign-off before the package is uploaded.

Verify the PyPI release at `https://pypi.org/project/pytribeam/` and test install with:

```sh
pip install pytribeam==1.0.0
```

## Manual Approval Gate

By default, a tag push triggers the full release pipeline automatically — including the final publish to PyPI — with no human checkpoint. The manual approval gate pauses the `publish` job and requires a named reviewer to explicitly approve before the package is uploaded to PyPI.

This is an industry-standard safeguard for production releases. It gives a release manager a final opportunity to confirm that the correct tag is being published, the changelog looks right, and no last-minute issues have been flagged.

The approval gate applies only to the production `pypi` environment. The `testpypi` environment (used for pre-releases) does not require approval, since pre-releases are low-risk by design.

### Setup (GitHub Settings UI)

No changes to `release.yml` are required. The `publish` job dynamically selects `environment: pypi` for stable releases or `environment: testpypi` for pre-releases — GitHub uses this environment name as the hook to enforce the approval rule.

* Navigate to the repository on GitHub.
* Click the **Settings** tab.
* In the left sidebar under **Code and automation**, click **Environments**.
* Click on the **pypi** environment.
* Under **Deployment protection rules**, check the box next to **Required reviewers**.
* In the text field that appears, type the GitHub username(s) or team name(s) who are authorized to approve a PyPI release. Add up to 6 reviewers.
* Click **Save protection rules**.

When a release tag is pushed, the pipeline will run `validate_tag`, `test`, `build`, and `github-release` automatically. The `publish` job will then pause with status **Waiting**. The designated reviewer(s) will receive a GitHub notification and must click **Review deployments → Approve and deploy** before the package is uploaded to PyPI.

If no reviewer approves within 30 days, the deployment times out and must be re-triggered.

## Release procedure (quick reference)

> Updated 7/9/26. The workflow no longer commits `_version.py` back to the branch,
> so the branch-protection workaround previously needed for PyPI releases is gone.
> Always push the branch **before** the tag (avoids the tag-validation race).

### Release candidate to TestPyPI (from `dev`)
- Ensure `dev` is up to date and pushed:
```bash
git checkout dev
git pull
git push origin dev
```
- Create and push the rc tag (routes to TestPyPI because it contains `rc`):
```bash
git tag -a v0.1.2rc1 -m "Release candidate 1 for version 0.1.2"
git push origin v0.1.2rc1
```
  - This triggers `release.yml`: validate → test → build → GitHub pre-release → publish to TestPyPI.

### Release to PyPI (from `main`)
- Ensure `main` contains the validated release commit and is pushed:
```bash
git checkout main
git pull origin main
git merge dev          # if the release content comes from dev
git push origin main
```
- Create and push the production tag (no `rc`/`dev` ⇒ routes to PyPI):
```bash
git tag -a v0.1.2 -m "Release version 0.1.2"
git push origin v0.1.2
```
  - This triggers the same pipeline but publishes a full GitHub Release and uploads to production PyPI (pausing for the manual approval gate if one is configured on the `pypi` environment).
