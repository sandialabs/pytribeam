As autoscript cannot be installed in a virtual environment and requires a license, content for githubpages must be generated locally on a licensed machine. This file contains instructions and commands to create content for github pages for the gh-pages branch.

# overwriting gh-pages

In order to manually overwrite the content of gh-pages, you should start from an up-to-date version of the "main" branch:

```sh
git switch main
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

## test coverage

## lint logs

## versioning