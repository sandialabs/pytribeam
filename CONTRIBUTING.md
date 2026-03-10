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

# both methods
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

We separate the concerns of test, build, release, and publish throughout the `.github/workflows/` files.

* **Test (Verification)**
  * **Purpose:** To ensure that the code is functional and hasn't introduced regressions (broken existing features).
  * **What happens:** Automated tools like `pytest` run your unit and integration tests. It often includes "linting" (checking code style) and type-checking.
  * **Key Outcome:** Confidence. If this stage fails, the process stops immediately, preventing broken code from ever reaching a user.
* **Build (Packaging)**
  * **Purpose:** To transform your "human-readable" source code into "machine-installable" artifacts.
  * **What happens:** Tools (like `python -m build`) bundle your code into standard formats, such as a Wheel (`.whl`) or a Source Distribution (`.tar.gz`).
   * **Key Outcome:** Portability. You now have a single file (an "artifact") that contains everything needed to install your library on any compatible system.
* **Release (Documentation & Tagging)**
   * **Purpose:** To create an official "point-in-time" snapshot of the project for project management and users.
   * **What happens:** A permanent Git tag (like v1.0.0) is assigned to a specific commit. A GitHub Release page is generated with a Changelog (i.e., What's New?) and the build artifacts are attached to it as "Release Assets."
  * **Key Outcome:** Traceability. It provides a clear history of the project's evolution and a stable place for users to download specific versions.
* **Publish (Distribution)**
   * **Purpose:** To make the software easily available to the global ecosystem.
   * **What happens:** The built artifacts are uploaded to a package registry, such as PyPI (the Python Package Index).
   * **Key Outcome:** Accessibility. Once published, anyone in the world can install your software using a simple command like `pip install pytribeam`.

Implementation details:

* The reuse of `test.yml` via a `workflow_call` ensures that test logic is not duplicated.
* **Dependency Chain:** `build` waits for `test`, and publish waits for both `build` and `github-release`.
* **Artifact Integrity:** By building once and downing the artifacts in subsequent jobs, we ensure the exact same files go to GitHub and PyPI.
* **Security:** We use `id-token: write` for PyPI's Trusted Publishing, which is a modern and secure way to handle authentication.

In `release.yml` we have removed the manual `-p ${{ secrets.PYPI_TOKEN }}`.  The industry standard is now [**Trusted Publishing**](https://docs.pypi.org/trusted-publishers/).  You configure this in your PyPI project settings once, and GitHub Actions authenticates securely without you needing to store and rotate secrets.

To configure Trusted Publishing, you tell PyPI, "Trust any code from this specific GitHub repository and workflow."  This removes the need to mange long-lived API tokens or passwords in your secrets.

Step:

* Log into your [PyPI](https://pypi.org) account
* Go your project's **Manage** page (or your accounts **Publishing** settings if you are setting it up for the first time.)
* Look for the **Publishing**tab
* Click **Add new publisher**
* Select **GitHub** as the source
* Enter the following details:
  * Owner: sandialabs
  * Repository name: pytribeam
  * Workflow name: `release.yml` (This must match your filename in your `.github/workflows/` directory))
  * Environment name: You can leave this blank or name it `pypi` (if you use it in your YAML).  We used `pypi`.
  * Click the **Add** button

To create a release:

* Merge the `dev` branch into the `main` branch.
* On the `main` branch, `git tag` and push to `main`, e.g., 

```sh
# Ensure you are on the main branch
git checkout main
git pull

# View existing tags, if any
git tag

# Create the new tag, e.g.,
git tag -a v1.0.0 -m "Release version 1.0.0"

# On the main branch, push the tag to GitHub
git push origin v1.0.0
```
