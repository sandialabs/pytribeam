# pyTriBeam

![main_logo](docs/userguide/src/logos/logo_color.png)

[![GitHub Pages][pages_badge]][pages_link] [![PyPI][pypi_badge]][pypi_link]   

Documentation and quality reports for pyTriBeam.

| 🚀 Released (main) | 🛠️ Development (dev) |
| :---: | :---: |
| [![**User's Manual**][manual_badge_main]][manual_main]            | [![**User's Manual**][manual_badge_dev]][manual_dev]  |
| [![**API Reference**][api_badge_main]][api_main]            | [![**API Reference**][api_badge_dev]][api_dev]                                 | [**API Reference**][api_dev] |
| [![Lint main][lint_badge_main]][lint_report_main]             | [![Lint dev][lint_badge_dev]][lint_report_dev] |
| [![Coverage main][coverage_badge_main]][coverage_report_main] | [![Coverage dev][coverage_badge_dev]][coverage_report_dev] |


## Getting Started

Installation instructions and more can be found in the User Guide ([Stable/main][manual_main] or [Latest/dev][manual_dev]).

## Citing ``pytribeam``

If ``pytribeam`` has been useful in your research, we invite you to cite the following paper on it's development and use:

Polonsky, A.T., Lamb, J.D., Hovey, C.B. et al. pyTriBeam: Open-Source Software for Enhanced 3D Data Collection in TriBeam Microscopes. Integr Mater Manuf Innov (2026). https://doi.org/10.1007/s40192-026-00449-2

Or using BibTeX:
```bibtex
@article{Polonsky2026,
  title = {pyTriBeam: Open-Source Software for Enhanced 3D Data Collection in TriBeam Microscopes},
  ISSN = {2193-9772},
  url = {http://dx.doi.org/10.1007/s40192-026-00449-2},
  DOI = {10.1007/s40192-026-00449-2},
  journal = {Integrating Materials and Manufacturing Innovation},
  publisher = {Springer Science and Business Media LLC},
  author = {Polonsky,  Andrew T. and Lamb,  James D. and Hovey,  Chad B. and Schroader,  Haydn and Echlin,  McLean P. and Pollock,  Tresa M.},
  year = {2026},
  month = feb 
}
```
## Contributing

See [here](https://github.com/sandialabs/pytribeam/blob/main/CONTRIBUTING.md) to learn more about how to contribute to the `pytribeam` community!

[manual_main]: https://sandialabs.github.io/pytribeam/main/docs/userguide/book/index.html
[manual_dev]: https://sandialabs.github.io/pytribeam/dev/docs/userguide/book/index.html

[manual_badge_main]: https://img.shields.io/badge/-User%20Guide-gray?logo=mdbook&logoColor=c4a484
[manual_badge_dev]: https://img.shields.io/badge/-User%20Guide-gray?logo=mdbook&logoColor=yellow

[api_main]: https://sandialabs.github.io/pytribeam/main/docs/api/index.html
[api_dev]: https://sandialabs.github.io/pytribeam/dev/docs/api/index.html

[api_badge_main]: https://shields.io/badge/-API%20Docs-gray?logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxOTIiIGhlaWdodD0iMTkyIj48cGF0aCBkPSJNNjcuODA3IDIzLjI0NGMtMTguMDMyIDUuNTIzLTI0LjI3MyA5LjQxMS0zMy4xOTMgMTYuMTY5UzE5LjQwNyA1MS4xMjUgOS4zNCA2OS43NkMzLjI3IDgwLjk5Ni44MjcgOTkuMjcxIDEgMTExLjY3OWMuMTE0IDguMTY5IDIuMTg4IDEzLjU1OSAyLjE4OCAxMy41NTlTNDIuMzI2IDI0Ny4yNyAyMC40MzUgMjc4LjEwNWMtMTAuNDg4IDE0Ljc3MyA4NC40MjIgMjcuMDA3IDgwLjA0NyAxMC40NS0xMC4zOTctMzkuMzQ4LTI3LjU5NS05Ny40MDktMzEuOTA4LTExMy42NjctMy4wNDctMTEuNDg0IDguMTYtMjEuOTk1IDE2LjI5NS0yNy4zNDMgMy4zODMtMi4yMjQgOC4wNTEtMy43ODYgOC4wNTEtMy43ODZsNTEuOTI0LTE1LjU5NXMyMy44MDktOC41NzkgMzQuMDYyLTI2LjU2NyAxMi42ODktMzcuNTg0IDEyLjY4OS0zNy41ODQuNDk1LTE2LjU4OC01LjkzOS0yMy4xNC0yLjczMi01Ljg2Ni0xOC42NDYtMTIuNDk4LTQ5LjEyMi0xMC4wNTMtNDkuMTIyLTEwLjA1My0zMi4wNDktLjYwMi01MC4wODEgNC45MjF6IiBmaWxsPSIjMjBhZDZjIi8+PGcgdHJhbnNmb3JtPSJyb3RhdGUoMzQzLjk5MykiPjxlbGxpcHNlIGN4PSI1Mi4yNzYiIGN5PSI5NC4wODkiIGZpbGw9IiNmZmYiIHJ4PSIyNy44NTIiIHJ5PSIyNy44MjMiLz48ZWxsaXBzZSBjeD0iNTIuNTM4IiBjeT0iOTQuNjg5IiByeD0iMTguNjg4IiByeT0iMTguMzMxIiBmaWxsPSIjMTA1YTQ4Ii8+PGVsbGlwc2UgY3g9IjYzLjMzMyIgY3k9Ijg2LjMiIGZpbGw9IiNmZmYiIHJ4PSI3LjU5NiIgcnk9IjcuNTg4Ii8+PC9nPjxnIGZpbGw9IiMxMDVhNDgiPjxlbGxpcHNlIGN4PSI5NC4xNTQiIGN5PSIxMzUuNzM0IiByeD0iNC41MDUiIHJ5PSI1LjI1NyIgdHJhbnNmb3JtPSJyb3RhdGUoMzI1LjAxNSkiLz48ZWxsaXBzZSBjeD0iMTY3Ljg2IiBjeT0iNTYuOTUxIiByeD0iNC40ODQiIHJ5PSI1LjIzMSIgdHJhbnNmb3JtPSJyb3RhdGUoMzU4Ljc3OSkiLz48L2c+PHBhdGggZD0iTTE4OC45NjIgNzcuNDU4bC0zNC4yNDggMTAuMTcxYy02Ljg3OCAxLjk3My05Ljk3NCAzLjM4OC0xNC44ODggMy42NnMtMTAuODY4LTEuODY5LTEwLjg2OC0xLjg2OWwtMi4zNDIgOC42MzNjMi4xOTcuOTQ0IDkuOTY5IDIuMzkgMTQuNzU2IDIuNTkyczE1LjU4Mi0yLjQ2IDE1LjU4Mi0yLjQ2bDI3LjQ3MS03LjUzNGMxLjk1MS00LjcwOSAzLjQzMi05LjIzOCA0LjUzNy0xMy4xOTN6IiBmaWxsPSIjZTc4MzYxIi8+PC9zdmc+
[api_badge_dev]: https://shields.io/badge/-API%20Docs-gray?logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxOTIiIGhlaWdodD0iMTkyIj48cGF0aCBkPSJNNjcuODA3IDIzLjI0NGMtMTguMDMyIDUuNTIzLTI0LjI3MyA5LjQxMS0zMy4xOTMgMTYuMTY5UzE5LjQwNyA1MS4xMjUgOS4zNCA2OS43NkMzLjI3IDgwLjk5Ni44MjcgOTkuMjcxIDEgMTExLjY3OWMuMTE0IDguMTY5IDIuMTg4IDEzLjU1OSAyLjE4OCAxMy41NTlTNDIuMzI2IDI0Ny4yNyAyMC40MzUgMjc4LjEwNWMtMTAuNDg4IDE0Ljc3MyA4NC40MjIgMjcuMDA3IDgwLjA0NyAxMC40NS0xMC4zOTctMzkuMzQ4LTI3LjU5NS05Ny40MDktMzEuOTA4LTExMy42NjctMy4wNDctMTEuNDg0IDguMTYtMjEuOTk1IDE2LjI5NS0yNy4zNDMgMy4zODMtMi4yMjQgOC4wNTEtMy43ODYgOC4wNTEtMy43ODZsNTEuOTI0LTE1LjU5NXMyMy44MDktOC41NzkgMzQuMDYyLTI2LjU2NyAxMi42ODktMzcuNTg0IDEyLjY4OS0zNy41ODQuNDk1LTE2LjU4OC01LjkzOS0yMy4xNC0yLjczMi01Ljg2Ni0xOC42NDYtMTIuNDk4LTQ5LjEyMi0xMC4wNTMtNDkuMTIyLTEwLjA1My0zMi4wNDktLjYwMi01MC4wODEgNC45MjF6IiBmaWxsPSIjZmZmZjAwIi8+PGcgdHJhbnNmb3JtPSJyb3RhdGUoMzQzLjk5MykiPjxlbGxpcHNlIGN4PSI1Mi4yNzYiIGN5PSI5NC4wODkiIGZpbGw9IiNmZmYiIHJ4PSIyNy44NTIiIHJ5PSIyNy44MjMiLz48ZWxsaXBzZSBjeD0iNTIuNTM4IiBjeT0iOTQuNjg5IiByeD0iMTguNjg4IiByeT0iMTguMzMxIiBmaWxsPSIjMTA1YTQ4Ii8+PGVsbGlwc2UgY3g9IjYzLjMzMyIgY3k9Ijg2LjMiIGZpbGw9IiNmZmYiIHJ4PSI3LjU5NiIgcnk9IjcuNTg4Ii8+PC9nPjxnIGZpbGw9IiMxMDVhNDgiPjxlbGxpcHNlIGN4PSI5NC4xNTQiIGN5PSIxMzUuNzM0IiByeD0iNC41MDUiIHJ5PSI1LjI1NyIgdHJhbnNmb3JtPSJyb3RhdGUoMzI1LjAxNSkiLz48ZWxsaXBzZSBjeD0iMTY3Ljg2IiBjeT0iNTYuOTUxIiByeD0iNC40ODQiIHJ5PSI1LjIzMSIgdHJhbnNmb3JtPSJyb3RhdGUoMzU4Ljc3OSkiLz48L2c+PHBhdGggZD0iTTE4OC45NjIgNzcuNDU4bC0zNC4yNDggMTAuMTcxYy02Ljg3OCAxLjk3My05Ljk3NCAzLjM4OC0xNC44ODggMy42NnMtMTAuODY4LTEuODY5LTEwLjg2OC0xLjg2OWwtMi4zNDIgOC42MzNjMi4xOTcuOTQ0IDkuOTY5IDIuMzkgMTQuNzU2IDIuNTkyczE1LjU4Mi0yLjQ2IDE1LjU4Mi0yLjQ2bDI3LjQ3MS03LjUzNGMxLjk1MS00LjcwOSAzLjQzMi05LjIzOCA0LjUzNy0xMy4xOTN6IiBmaWxsPSIjZTc4MzYxIi8+PC9zdmc+

[lint_badge_main]: https://sandialabs.github.io/pytribeam/main/badges/lint.svg
[lint_badge_dev]: https://sandialabs.github.io/pytribeam/dev/badges/lint.svg

[lint_report_main]: https://sandialabs.github.io/pytribeam/main/reports/lint/index.html
[lint_report_dev]: https://sandialabs.github.io/pytribeam/dev/reports/lint/index.html

[coverage_badge_main]: https://sandialabs.github.io/pytribeam/main/badges/coverage.svg
[coverage_badge_dev]: https://sandialabs.github.io/pytribeam/dev/badges/coverage.svg

[coverage_report_main]: https://sandialabs.github.io/pytribeam/main/reports/coverage/index.html
[coverage_report_dev]: https://sandialabs.github.io/pytribeam/dev/reports/coverage/index.html

[pypi_badge]: https://img.shields.io/pypi/v/pytribeam?logo=pypi&logoColor=FBE072&label=PyPI&color=4B8BBE
[pypi_link]: https://pypi.org/project/pytribeam

[pages_badge]: https://img.shields.io/badge/GitHub%20Pages-blueviolet?logo=github
[pages_link]: https://sandialabs.github.io/pytribeam/
