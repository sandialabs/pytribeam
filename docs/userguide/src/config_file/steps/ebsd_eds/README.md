# EBSD and EDS Settings

Settings for EBSD and EDS type steps are exactly equivalent to those for Image type steps. Settings for imaging conditions can be found [here](../image/index.html).

Automation for the insertion and removal of these detectors, as well as starting collection of the maps with the 3rd party vendor are included in these special step types and require no additional parameters in the ``pytribeam`` configuration file. However, due to current limitations in API access across vendors, users must setup their own maps independently, and only one map type is supported at this time. Therefore, users cannot create experiment pipelines that contain both EBSD and EDS type steps (only one or the other), which is enforced by validation at run time. However, both supported vendors do offer the capability to concurrently capture EDS spectra with EBSD patterns, which users can set up independently prior to inititaing an experiment.

The only difference in settings from a standard Image step type applies specifically to EBSD type steps, which have one additional parameter:

- **concurrent_EDS** (*bool*): needed to ensure we insert and retract both detectors
