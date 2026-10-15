# Introduction

![Project Logo](logos/logo_color.png)

`pytribeam` provides tools for automated acquisition of data on the TriBeam scanning electron microscope using Thermo Fisher Scientific's `autoscript` API, which provides a `python` interface for microscope interactions. `pytribeam` is geared specifically for 3D data collection with the use of an integrated femtosecond laser, but offers many higher-level functionalities applicable to single SEM or dual-beam SEM/FIB (both Gallium and Xenon Plasma) platforms utilizing `autoscript`.

Utilization of this tool does not require advanced experience with `python`, but it is generally expected that users will be experienced in the use and operation of the microscope platform and understand the various steps required to create workflows for automated data collection. This package assumes users are able to orient and place their sample at the eucentric position within the microscope, and are able to determine various machine settings (including, but not limited to, detector selection and settings, determination of milling geometries and settings, etc.) required for automated data collection.

