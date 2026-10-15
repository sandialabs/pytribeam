Bruker EDS Mapping Productionization Plan
Current state summary
We have established a working Python path for Bruker EDS mapping using direct ctypes bindings to the native Bruker ESPRIT API DLLs.
Current interface approach:

Load Bruker DLLs directly:
Bruker.API.Esprit64.dll
Bruker.API.Logging64.dll


Use ctypes.WinDLL
Define function signatures from Bruker C/C++ headers
Wrap return-code based API calls in Python controller classes
Use GetDebugErrorString where possible
Keep Bruker implementation siloed under external_oem.bruker

This approach is already working for basic hardware EDS mapping.

Proven capabilities
Session / API connection
Working:

local OpenClient
CheckConnection
QueryInfo
persistent session behavior
explicit output paths for save operations

Important operational note:

closing API connections can affect ESPRIT GUI state
production workflow should default to persistent sessions:
connect once
run workflow
optionally close only if configured




EDS detector motion
Working / partially validated:

EDSGetDetectorPosition
EDSSetDetectorPosition
detector position states:
park
acquire



Important hardware finding:

EDS detector has only coarse state:
park
acquire


acquire may encompass multiple physical insertion positions
therefore, detector position is a safety/mechanical check, not a data-quality guarantee

Production rule:

verify park at start/end when configured
move to acquire before map
move to park after map
validate data quality from output/readback, not from detector state alone


Basic EDS HyperMap acquisition
Working:

ImageSetConfiguration
HyMapStart
HyMapGetStateEx
HyMapStop
HyMapSaveToFile
explicit .bcf output paths
HyMapGetImage map image export

Notes:

simple full-frame maps work
explicit output paths work better than relying on ESPRIT project/user-data conventions
.bcf files may remain locked by ESPRIT, so tests should avoid immediate byte reads


EDS profile / element map acquisition
Working:

TRTHyMapProfileSettings
TRTElementRegion
HyMapCreateProfile
HyMapStartWithProfile
custom element list from Python
profile XML generation
.bcf save
image export

Confirmed:

Python can define requested EDS elements
HyMapCreateProfile returns valid XML
HyMapStartWithProfile runs on simulator/hardware
element numeric data can be extracted with HyMapGetElementData


EDS element map numeric readback
Working for moderate map sizes:

HyMapGetElementData
returns numeric element planes
observed format:
uint16
shape (height_px, width_px)
byte size width * height * 2


element indices are zero-based
element index matches order of requested settings.elements

Important finding:

rendered colors are unreliable / Bruker-display-specific
numeric data are the authoritative output
default/display colors should be treated as visualization hints only

Production rule:

rely on numeric arrays from HyMapGetElementData
save element arrays to HDF5 or .npy
optionally save rendered BMPs as preview artifacts
do not rely on Bruker-rendered color semantics


.spx spectrum handling
Working, but not primary focus now:

.spx generated via CreateSpectrum
.spx is XML-based
parseable directly in Python
<Channels> contains counts

Current priority is EDS maps, not single spectra.

Known issues / risks
1. High-resolution HyMapGetElementData failure
Observed on hardware:

map acquisition completed
.bcf saved
failure occurred during readback with HyMapGetElementData
resolution: 1000 x 666
elements: 7
error:
OSError: [WinError 250477278] Windows Error 0xeedfade



Likely interpretation:

Bruker-side Delphi/C++ exception crossing DLL boundary
likely triggered by:
large map size
many elements
buffer behavior
unsupported line string
internal API readback limit
memory/stride/resolution constraint



This needs to be run to ground.

2. .bcf file locking
Observed:

.bcf save succeeds
file exists
file size is nontrivial
immediate read_bytes() can raise PermissionError
even after CloseConnection, file may remain locked

Production/testing implication:

do not require immediate direct .bcf reads in integration tests
validate .bcf by:
API success
exists
nontrivial size


direct .bcf parsing is deferred unless Bruker documents format or file-lock behavior is resolved


3. Reduced-area mapping not fully formalized
Likely supported via:

HyMapStartEx
HyMapStartWithProfile
TFeatureData
TSegment

We currently construct rectangular segment regions for profile maps, but need to formalize ROI/reduced-area scan support.
Need to test:

full-frame map
rectangular ROI
non-origin ROI
boundary conditions
max segment counts
interaction between ImageSetConfiguration dimensions and ROI dimensions


4. Profile map acquisition duration
Known issue:

HyMapStart has RealTime
HyMapStartWithProfile signature in provided headers does not expose RealTime
profile map acquisition appears to behave like one scan or profile-driven acquisition

Need to clarify:

whether HyMapStartWithProfile always performs one scan
whether acquisition time/frames are encoded in profile XML
whether another API variant exists


5. Raw spectral cube readback not solved
We have numeric element maps, but not full raw spectral cube extraction yet.
Potential API calls:

HyMapGetXYSpectrum
HyMapGetLineSpectra
HyMapGetCompressedLineSpectra
HyMapLoadFromFile

Current status:

HyMapGetXYSpectrum returns header-only
line-spectra APIs still need implementation/testing

This is important if the final production workflow needs raw spectra, not just element planes.

Immediate productionization goal
Productionize Bruker EDS mapping only inside the broader external_oem submodule.
Do not expand EBSD production support yet.
Scope for this production pass:

Bruker session management
EDS detector motion
EDS full-frame map
EDS profile/element map
reduced-area rectangular mapping
numeric element-map readback
structured YAML config ingestion
structured logging
HDF5-compatible output design
simulator and hardware test suites


Proposed module structure
Current/target package structure:

text
src/
  pytribeam/
    external_oem/
      core/
        errors.py
        vendor.py
      bruker/
        __init__.py
        bindings.py
        ctypes_types.py
        types.py
        session.py
        detector_motion.py
        eds.py
        config.py
        workflow.py
        readback.py
        tools/
          bruker_eds_yml_hardware_validation.py

Test structure:

text
tests/
  bruker/
    conftest.py
    helpers.py
    unit/
      test_types.py
      test_session.py
      test_detector_motion.py
      test_eds.py
      test_config.py
      test_workflow.py
    integration/
      test_session_integration.py
      test_eds_map_integration.py
      test_eds_profile_map_integration.py
      test_hymap_image_integration.py
      test_bcf_integration.py
    hardware/
      test_eds_detector_motion_hardware.py
      test_eds_mapping_hardware.py
      test_eds_resolution_matrix_hardware.py


Suggested implementation plan for Continue.dev / agentic workflow
Use small, controlled tasks with git commits after each step. Keep each change reviewable.

Phase 0 — Stabilize current EDS implementation
Commit 0.1 — Snapshot current working state
Goal:

create baseline commit before refactors

Agent task:

no functional changes
ensure code is formatted
commit current working Bruker EDS mapping state

Commit message:

text
chore(bruker): snapshot working EDS mapping prototype


Phase 1 — Clean EDS types and controller API
Commit 1.1 — Normalize Bruker EDS settings types
Goal:

make current NamedTuple settings stable
remove required color settings from scientific config
keep display colors optional

Types to ensure:

python
BrukerSessionSettings
BrukerDetectorMotionSettings
BrukerEDSMapSettings
BrukerEDSElementMapSetting
BrukerEDSProfileMapSettings
BrukerMapProgress
BrukerMapOutputs

Element setting should look conceptually like:

python
class BrukerEDSElementMapSetting(NamedTuple):
    atomic_number: int
    line: str
    energy_keV: float = 0.0
    width: float = 1.0
    display_rgb: Optional[Tuple[int, int, int]] = None

Acceptance criteria:

existing EDS sandbox still runs
unit tests pass

Commit message:

text
refactor(bruker): stabilize EDS settings types


Commit 1.2 — Add progress/time logging support
Goal:

add log_fn callbacks to map acquisition methods
log elapsed time, percent, current line, estimated remaining time

Methods:

BrukerEDSController.acquire_map
BrukerEDSController.acquire_map_with_profile

Progress report should include:

elapsed seconds
percent complete
current line
estimated remaining seconds if percent > 0

Acceptance criteria:

no behavior change if log_fn=None
hardware validation script prints useful progress in Python

Commit message:

text
feat(bruker): add EDS map progress time logging


Phase 2 — Formalize EDS element map readback
Commit 2.1 — Harden HyMapGetElementData readback
Goal:

implement robust numeric element map readback
avoid all-or-nothing failure when one element fails
use exact expected byte size first

Methods:

python
get_element_data_bytes(...)
get_element_data_array(...)
read_profile_element_maps(...)
save_profile_element_maps_npy(...)

Enhancements:

exact expected buffer size: width * height * 2
fallback to larger buffers if needed
per-element error capture
optional strict/non-strict behavior

Consider adding result type:

python
class BrukerElementReadbackResult(NamedTuple):
    element_index: int
    atomic_number: int
    line: str
    path: Optional[str]
    shape: Optional[Tuple[int, int]]
    dtype: Optional[str]
    min: Optional[int]
    max: Optional[int]
    sum: Optional[int]
    nonzero: Optional[int]
    error: Optional[str]

Acceptance criteria:

moderate profile maps still save .npy
high-resolution failures are logged per element, not crashing entire workflow
summary JSON records failures

Commit message:

text
feat(bruker): add robust EDS element map readback


Commit 2.2 — Add element readback diagnostics
Goal:

save metadata JSON alongside .npy
record stats:
min
max
sum
nonzero
dtype
shape
element metadata



Acceptance criteria:

hardware validation produces .npy and metadata JSON
results can be inspected without ESPRIT

Commit message:

text
feat(bruker): write EDS element map readback metadata


Phase 3 — Reduced-area mapping
Commit 3.1 — Add rectangular ROI settings
Goal:

support reduced-area rectangular scans

Add type:

python
class BrukerRectROI(NamedTuple):
    x_start_px: int
    y_start_px: int
    width_px: int
    height_px: int

Add optional field to map/profile settings:

python
roi: Optional[BrukerRectROI]

Implementation:

full-frame uses existing behavior
ROI maps build TFeatureData with one TSegment per row

Acceptance criteria:

ROI at origin works
non-origin ROI works in simulator/hardware if supported
logs actual ROI and dimensions

Commit message:

text
feat(bruker): add rectangular ROI mapping support


Commit 3.2 — Add image configuration readback
Goal:

bind ImageGetConfiguration
after ImageSetConfiguration, log/read back accepted width/height/pixel time/channel flags

Acceptance criteria:

hardware script reports requested vs accepted map dimensions
helps diagnose 1000 x 666 failures

Commit message:

text
feat(bruker): read back configured EDS image settings


Phase 4 — Spectrometer status / CPS / detector health
Commit 4.1 — Add spectrometer status bindings
Goal:

bind relevant status functions:
GetSpectrometerStatus
GetSpectrometerConfiguration
GetSpectrometerRanges
maybe GetSpectrometerParam



Need to add ctypes structs:

TRTDetectorStatus
TRTSpectrometerStatus
TRTDetectorRanges

Expose methods:

python
get_spectrometer_status(spu: int)
get_spectrometer_configuration(spu: int)
get_spectrometer_ranges(spu: int, det: int)

Acceptance criteria:

sandbox logs count rate / temperature / detector status if available
no requirement yet for dead time unless API provides it

Commit message:

text
feat(bruker): add EDS spectrometer status queries


Commit 4.2 — Add pre/post acquisition status logging
Goal:

record detector status before and after acquisition
optionally during progress polling if available

Acceptance criteria:

hardware validation log includes spectrometer state snapshots

Commit message:

text
feat(bruker): log EDS spectrometer status around maps


Phase 5 — YAML configuration ingestion
Commit 5.1 — Add Bruker EDS config parser
Goal:

formalize YAML ingestion into immutable NamedTuple settings
no raw dicts beyond parser

Module:

text
bruker/config.py

Functions:

python
load_bruker_eds_yaml(path) -> BrukerEDSWorkflowSettings

Add settings:

python
BrukerEDSWorkflowSettings
BrukerEDSOutputSettings
BrukerEDSReadbackSettings

Acceptance criteria:

parses current validation YAML
unit tests for config parsing
clear validation errors

Commit message:

text
feat(bruker): add YAML parser for EDS workflows


Commit 5.2 — Add Bruker EDS workflow runner
Goal:

move hardware validation orchestration out of script and into module

Module:

text
bruker/workflow.py

Function:

python
run_bruker_eds_workflow(settings, log_fn=None) -> BrukerEDSWorkflowResult

Responsibilities:

connect/session
detector park/acquire
map acquisition
readback
output summary
optional close

Script becomes thin wrapper:

python
settings = load_bruker_eds_yaml(path)
run_bruker_eds_workflow(settings, log_fn=logger)

Acceptance criteria:

existing YAML hardware validation still works
script contains minimal orchestration

Commit message:

text
feat(bruker): add EDS workflow runner


Phase 6 — Hardware resolution/error investigation
Commit 6.1 — Add resolution matrix hardware script
Goal:

systematically test map size/readback failure

Script or workflow mode:

yaml
resolution_matrix:
  - width_px: 500
    height_px: 300
    elements: ...
  - width_px: 750
    height_px: 500
    elements: ...
  - width_px: 1000
    height_px: 666
    elements: ...

Record:

acquisition success
.bcf size
readback success per element
exception / rc
requested vs accepted ImageGetConfiguration
elapsed time

Acceptance criteria:

one command produces matrix summary JSON/CSV

Commit message:

text
feat(bruker): add EDS hardware resolution matrix runner


Commit 6.2 — Add line-string test matrix
Goal:

compare line strings:
K
KA
LA
etc.



Purpose:

determine whether generic line labels behave differently from canonical labels

Acceptance criteria:

output summary comparing acquisition/readback stats

Commit message:

text
feat(bruker): add EDS line-string validation workflow


Phase 7 — HDF output design
Do after YAML runner is stable.
Commit 7.1 — Add HDF writer skeleton
Likely dependency:

h5py

Design:

text
/run_info
/settings
/log
/native_files
/eds/maps/{element_index}/data
/eds/maps/{element_index}/attrs
/eds/previews

Acceptance criteria:

writes one HDF per run
stores:
copied YAML
query info
element arrays
element metadata
native file paths
logs



Commit message:

text
feat(bruker): add HDF output writer for EDS maps


Simulator and hardware test strategy
Simulator tests
Should run without hardware but with ESPRIT simulator.
Focus:

session connect
simple map
profile map
.bcf existence/size
.bmp export
element data readback at small resolution
YAML parse + workflow dry run or small map

Avoid:

direct .bcf read assertions
detector motion unless simulator supports it

Markers:

python
@pytest.mark.esprit


Hardware tests
Should be explicitly marked:

python
@pytest.mark.esprit
@pytest.mark.hardware

Focus:

EDS detector acquire/park
known-small map
profile map with known sample elements
element numeric arrays not all zero
resolution matrix
ROI maps

Do not require:

perfect color rendering
immediate .bcf file reads


Questions / checks for Bruker OEM
Send separately, but the most important for production are:

HyMapGetElementData
official dtype?
shape?
index convention?
size/resolution limits?


HyMapStartWithProfile
how to control acquisition time / number of frames?


reduced area mapping
recommended use of TFeatureData segments?
coordinate constraints?


spectrometer status
recommended live CPS/dead-time APIs during HyperMap?


.bcf
file locking behavior
recommended readback/export route


raw spectra
recommended way to extract raw spectral cube
HyMapGetCompressedLineSpectra usage




Short-term next action list
If using Continue.dev agentic work, I would start with this sequence:

Commit current state
Add progress/time logging
Harden element readback exact-size/per-element
Add image configuration readback
Add rectangular ROI support
Add YAML parser module
Move validation script into workflow runner
Create resolution matrix hardware runner
Only then start HDF output work

This keeps each step small and testable while preserving your current working hardware workflow.
