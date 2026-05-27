# External OEM scripting structure

Goal is to use a single dispatch style. Pass a certain set of parameters that triggers the specific OEM.

```
external_oem/
├──  __init__.py   # handle routing between different OEMs here maybe?
├──  com.py        # generalized communication protocols for all OEMs
|
├──  bruker/
|    ├──  ebsd.py  # all EBSD relevant methods
|    ├──  eds.py   # all EDS relevant methods
|    └──  util.py  # any other functions that are usefull
|
├──  edax/
|    ├──  ebsd.py  # ...
|    ├──  eds.py   # ... 
|    └──  util.py  # ...
|
└──  oxford/
     ├──  ebsd.py  # ...
     ├──  eds.py   # ...
     └──  util.py  # ...
```

### Outstanding questions

- Where to put the routing/dispatching?
- What overlap is there between APIs?
- Is additional functionality outside of EBSD/EDS needed?
- What happens when we want to default back to using the basic Thermo Fisher LaserControl functionality? Does that go in here or elsewhere?
