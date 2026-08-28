#!/usr/bin/python3
"""
EDAX IPAPI Package
==================

Wrapper for the EDAX IPAPI (TEAM/APEX) TCP command interface, as described in
the *EDAX IP / API Reference*, revision 2.3.8.

The package is layered so that each layer is testable on its own:

- :mod:`~pytribeam.external_oem.edax.types` -- enums and named tuples for the
  command vocabulary, parameters, and device states.
- :mod:`~pytribeam.external_oem.edax.errors` -- the exception hierarchy.
- :mod:`~pytribeam.external_oem.edax.protocol` -- pure command formatting and
  response parsing, with no I/O.
- :mod:`~pytribeam.external_oem.edax.client` -- the socket transport, which
  demultiplexes asynchronous events from command responses.
- :mod:`~pytribeam.external_oem.edax.base` -- behavior shared by the EDS and
  EBSD halves of the API.
- :mod:`~pytribeam.external_oem.edax.ebsd`, :mod:`~pytribeam.external_oem.edax.eds`,
  and :mod:`~pytribeam.external_oem.edax.sem` -- the device controllers.

Only :mod:`~pytribeam.external_oem.edax.workflow` depends on AutoScript, so
everything else imports and unit-tests on a machine without a microscope.

Examples
--------
>>> from pytribeam.external_oem.edax import EdaxClient, EdaxConnectionSettings
>>> from pytribeam.external_oem.edax import EdaxEbsdController
>>> settings = EdaxConnectionSettings(host="192.168.0.10")
>>> with EdaxClient(settings) as client:
...     ebsd = EdaxEbsdController(client)
...     print(ebsd.camera_status())
"""

from pytribeam.external_oem.edax.base import EdaxMappingController, TICKS_PER_SECOND
from pytribeam.external_oem.edax.client import EdaxClient
from pytribeam.external_oem.edax.ebsd import EdaxEbsdController
from pytribeam.external_oem.edax.eds import EdaxEdsController
from pytribeam.external_oem.edax.errors import (
    EdaxCommandError,
    EdaxConnectionError,
    EdaxError,
    EdaxResponseError,
    EdaxStateError,
    EdaxTimeoutError,
)
from pytribeam.external_oem.edax.sem import EdaxSemController
from pytribeam.external_oem.edax.types import (
    EdaxAccessType,
    EdaxCameraCapabilities,
    EdaxCameraInfo,
    EdaxCameraLimits,
    EdaxCameraParams,
    EdaxCameraSlidePositions,
    EdaxCameraStatus,
    EdaxCommand,
    EdaxConnectionSettings,
    EdaxDetectorSlideStatus,
    EdaxDetectorStatus,
    EdaxEbsdMapParams,
    EdaxEbsdMode,
    EdaxEbsdResolution,
    EdaxEdsMapParams,
    EdaxEvent,
    EdaxGridType,
    EdaxLimit,
    EdaxMappingStatus,
    EdaxProjectInfo,
    EdaxResponse,
    EdaxSemState,
    EdaxSettings,
)

__all__ = [
    "TICKS_PER_SECOND",
    "EdaxAccessType",
    "EdaxCameraCapabilities",
    "EdaxCameraInfo",
    "EdaxCameraLimits",
    "EdaxCameraParams",
    "EdaxCameraSlidePositions",
    "EdaxCameraStatus",
    "EdaxClient",
    "EdaxCommand",
    "EdaxCommandError",
    "EdaxConnectionError",
    "EdaxConnectionSettings",
    "EdaxDetectorSlideStatus",
    "EdaxDetectorStatus",
    "EdaxEbsdController",
    "EdaxEbsdMapParams",
    "EdaxEbsdMode",
    "EdaxEbsdResolution",
    "EdaxEdsController",
    "EdaxEdsMapParams",
    "EdaxError",
    "EdaxEvent",
    "EdaxGridType",
    "EdaxLimit",
    "EdaxMappingController",
    "EdaxMappingStatus",
    "EdaxProjectInfo",
    "EdaxResponse",
    "EdaxResponseError",
    "EdaxSemController",
    "EdaxSemState",
    "EdaxSettings",
    "EdaxStateError",
    "EdaxTimeoutError",
]
