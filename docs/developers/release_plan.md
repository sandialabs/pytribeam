# Release targets for `v1.0.0`

**~~Strikethrough~~ compeleted tasks, please**

## User support
**Andrew**
- adjust install/pyproject.toml to support Autoscript 4.10 python version 3.??

## infrastructure
**Andrew**
- setup virtual machines on workstation
  - one machine for each autoscript version

## deployment
**Chad**
- create ci/cd workflows to automate everything possible, including:
  - userguide (mdbook)
  - api docs (pdoc)
  - release, versioning, publish to pypi, update gh-pages branch

**James**
- figure out if we can install pytribeam in .venv
- create python-->bash script to automate things locally including:
  - testing
    - auto add location of root directory to the .coveragerc?
  - linting

## test improvements

**Andrew**
- Stop test suite on hard ware if test fails
    - insert/rectract EBSD is not self contained if it fails
- check for test independence 
- order tests in increasing complexity
- some tests won't work on some systems (CBS stage restrictions)
- need decorators for:
    - offline machines
    - machines with lasers
    - machines with CBS stage restriction locks (only the windows 7 Helios)
    - machine that doesn't fit into above (a fib with newer XtUI software)
- Some kind of cleanup/setup procedure before/after hardware tests:
    - lock/unlock laser objective
    - move laser objective to safe position
    - stage start pos/end pos
    - beam voltages on/off
    - all detectors retracted
- Track all machine types in constants
- setup environment for different AS version
- multi-AS version support: can we require 100% code coverage on specific functions?
  - can require code coverage amounts on files

**James**
- GUI tests

## State Recorder
**James**
- Adapter functions for pytribeam?
  
## Version support up to 4.11
**Andrew**
- deal with breaking change on detector insertable issue
  - propagate enum to other functions that call this



## Features (near- and long-term)
- multi-quad images
  - insert everything before ACB
- custom autofocus/autostig
- record beam shifts
- state recorder update
- EDAX API testing
- Bruker API support
- Oxford API support
- FIB serial sectioning 
  
## List of API requests

- Multi quad imaging at custom resolution
- FIB shutter support
