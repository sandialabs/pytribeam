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

* [`test-docker.yml`](/.github/workflows/test-docker.yml) — runs on every push to any branch
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
    * **What happens:** After tests pass, `test-docker.yml` builds the user guide with `mdbook`, generates badges and HTML reports, and deploys them to the `gh-pages` branch under a `dev/` or `main/` subdirectory so both coexist.
    * **Key Outcome:** Up-to-date documentation is always available for both the development and released versions of the project.
  * **Build (Packaging)**
    * **Purpose:** To transform your "human-readable" source code into "machine-installable" artifacts. This is the bridge between CI and CD. Once the code is verified (integrated), it can be packaged into a deployable format (Wheels/SDists).
    * **What happens:** Tools (like `python -m build`) bundle your code into standard formats, such as a Wheel (`.whl`) or a Source Distribution (`.tar.gz`).
    * **Key Outcome:** Portability. You now have a single file (an "artifact") that contains everything needed to install your library on any compatible system.
  * **Update Version File**
    * **Purpose:** To ensure that users who download a zip archive (without git metadata) still get the correct version number when installing.
    * **What happens:** After a successful build, `_version.py` is regenerated with the tagged version and committed back to the branch the tag was cut from (`main` or `dev`).
    * **Key Outcome:** Zip installs report the correct version rather than failing or falling back to a placeholder.
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

* The reuse of `test-docker.yml` via a `workflow_call` in `release.yml` ensures that test logic is not duplicated.
* **Dependency Chain:** `test` waits for `validate_tag`; `build` waits for `test`; `update-version-file` and `github-release` both wait for `build` and run in parallel; `publish` waits for both `build` and `github-release`.
* **Artifact Integrity:** By building once and downloading the artifacts in subsequent jobs, we ensure the exact same files go to GitHub and PyPI.
* **Security:** We use `id-token: write` for PyPI's Trusted Publishing, which is a modern and secure way to handle authentication.

### Trusted Publishing

In `release.yml` we have removed the manual `-p ${{ secrets.PYPI_TOKEN }}`.  The industry standard is now [**Trusted Publishing**](https://docs.pypi.org/trusted-publishers/) (also called OpenID Connect or OIDC).  You configure this in your PyPI project settings once, and GitHub Actions authenticates securely without you needing to store and rotate secrets.

> OpenID Connect (OIDC) provides a flexible, credential-free mechanism for delegating publishing authority for a PyPI package to a trusted third party service, like GitHub Actions.  PyPI users and projects can use trusted publishers to automate their release processes, without needing to use API tokens or passwords.

To configure Trusted Publishing, you tell PyPI, "Trust any code from this specific GitHub repository and workflow."  This removes the need to mange long-lived API tokens or passwords in your secrets.

Steps:


* In `release.yml`, the environment must be set to either `pypi` or `testpypi` depending on the version string.  Hence the logic in `release.yml`:

```yaml
environment: ${{ (contains(github.ref, 'rc') || contains(github.ref, 'dev')) && 'testpypi' || 'pypi' }}
```

Tags containing `rc` or `dev` (e.g., `v0.0.9rc1`, `v1.0.0.dev1`) route to TestPyPI. All other tags route to production PyPI. The `repository-url` in the publish step is set conditionally by the same logic.

The GitHub repository itself must have both a `pypi` and a `testpypi` environment:

On the GitHub repo:

* Click on the **Settings** tab (usually the last tab on the right in the top navigation bar).
* On the left-hand sidebar, look for the **Environments** link (it's under the "Code and automation" section).
  * If the environment doesn't exist yet:
    * Click the **New environment** button.
    * Name the environment `pypi` (and then make a second item called `testpypi`) and click **Configure environment**.
  * If it does exist but is named differently, you can click on it to rename it or delete it and create a new one.
* For a basic setup using Trusted Publishing, you don't actually need to add any secrets or configuration on this page. Just having the environment named testpypi exist is enough to link it to your workflow.
* Optionally, we add the following protections:
  * Under the **Deployment branches and tags**, under the **No Restriction** button, select **Selected branches and tags**.
  * Click **Add deployment branch or tage rule**.
  * Select **Ref type: Tag**.
  * Set the **Name Pattern:** to 'v*'.  This ensures that *only* version tags can ever use this environment, adding a layer of security.

Finally, the PyPI (respectively, Test PyPI) site needs to be configured.

* Log into your [PyPI](https://pypi.org) (or [Test PyPI](https://test.pypi.org)) account
* Go your project's **Manage** page (or your accounts **Publishing** settings if you are setting it up for the first time.)
* Look for the **Publishing** tab
* Click **Add new publisher**
* Select **GitHub** as the source
* Enter the following details:
  * Owner: sandialabs
  * Repository name: pytribeam
  * Workflow name: `release.yml` (This must match your filename in your `.github/workflows/` directory))
  * Environment name: You can leave this blank or name it `pypi` (if you use it in your YAML).  We used `pypi` for live publishing to the PyPI site, and `testpypi` for test publishing to the TestPyPI site.
  * Click the **Add** button

We follow PEP 440 (the Python standard for versioning), which requires version strings to follow this specific structure:

```bash
bashN.N.N[{a|b|rc}N][.postN][.devN]
```

Version strings are generated automatically by `hatch-vcs` (which uses `setuptools-scm` under the hood) via `git describe --tags`. For example, a version of `0.0.9.dev173` means:

* `0.0.9` — the most recent git tag
* `dev173` — 173 commits have been made since that tag

Each new commit increments the distance by 1. When a commit is tagged (e.g., `v0.1.0`), the distance resets to zero and the version becomes the clean `0.1.0` with no `.dev` suffix. This version is written to `src/pytribeam/_version.py` at build time and committed back to the repo by `release.yml` on each tagged release, so that zip archive installs also report the correct version.

## Manual Release

### Publish to TestPyPI (pre-release on `dev`)

Use this path to validate the full release pipeline — build, attestation, GitHub Release, and PyPI publish — without touching the production package index. Tags containing `rc` or `dev` are automatically routed to TestPyPI by `release.yml`.

```sh
# Ensure you are on the dev branch and up to date
git checkout dev
git pull

# View existing tags to choose the next version
git tag

# Regenerate _version.py so the committed file matches the tag you are about to create.
# This ensures zip archive installs report the correct version.
uv build

# Stage and commit _version.py if it changed
git add src/pytribeam/_version.py
git diff --staged --quiet || git commit -m "chore: update _version.py pre-release"

# Create a release candidate tag (rc) — this routes to TestPyPI
git tag -a v0.0.9rc1 -m "Release candidate 1 for version 0.0.9"

# Push the tag to GitHub — this triggers release.yml
git push origin v0.0.9rc1
```

After pushing, `release.yml` will:
1. Validate the tag (branch, PEP 440, version ordering)
2. Run the full test suite
3. Build the wheel and sdist with SLSA attestation
4. Create a GitHub Release marked as **pre-release**
5. Publish to **TestPyPI** (because the tag contains `rc`)
6. Commit the updated `_version.py` back to `dev`

Verify the TestPyPI release at `https://test.pypi.org/project/pytribeam/` and test install with:

```sh
pip install --index-url https://test.pypi.org/simple/ pytribeam==0.0.9rc1
```

### Publish to PyPI (production release on `main`)

Once the pre-release is validated, merge `dev` into `main` and tag a production release. Tags without `rc` or `dev` are routed to production PyPI.

```sh
# Merge dev into main
git checkout main
git merge dev
git push origin main

# View existing tags to confirm the next version
git tag

# Regenerate _version.py so the committed file matches the tag you are about to create
uv build

# Stage and commit _version.py if it changed
git add src/pytribeam/_version.py
git diff --staged --quiet || git commit -m "chore: update _version.py pre-release"

# Create the production release tag — this routes to PyPI
git tag -a v1.0.0 -m "Release version 1.0.0"

# Push the tag to GitHub — this triggers release.yml
git push origin v1.0.0
```

After pushing, `release.yml` will run the same pipeline as above but create a **full release** on GitHub and publish to **production PyPI**.
