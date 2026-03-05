# Release targets for `v1.0.0`

## test improvements

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
- auto add location of root directory to the .coveragerc?
- GUI tests
- Track all machine types in constants
  
## deployment

- create ci/cd workflows to automate everything possible, including:
  - docs
  - api docs
  - release, versioning, publish to pypi
 
- create bash script to automate things locally including:
  - testing
  - linting

## Version support up to 4.11
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
