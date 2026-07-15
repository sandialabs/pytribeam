## Development / Testing Notes

The state recorder reads a broad microscope state tree and may interact with the
microscope control UI while doing so. The GUI-side state recording is performed
in a background thread so the recorder window remains responsive, but the
underlying microscope/OEM control software may still pause, block, or defer API
responses depending on microscope activity.

### Behavior to test

Test state recording during or around the following microscope/control states:

- Idle microscope state.
- Active SEM imaging.
- Active FIB imaging.
- Rapid switching between imaging quadrants/views.
- Open microscope UI drop-down menus or active UI controls.
- FIB patterning setup, queued patterning, and active pattern execution.
- External control by EBSD software.
- External control by EDS software.
- Other external control or automation clients connected to the microscope.
- Vacuum/gas operations, if relevant.
- Stage movement or stage tilt/rotation operations.
- Detector insertion/retraction or detector setting changes.
- Error or warning states in the microscope control software.
- Network interruption or delayed microscope API responses.

### Specific questions to answer

- Does a state read block, fail, or wait while FIB patterning is active?
- Does a state read interfere with patterning execution or pattern queue state?
- Does a state read block, fail, or wait while EBSD/EDS software has external
  control?
- Does connecting/reconnecting for each state read cause any noticeable
  microscope-side delay or UI interruption?
- Does the active imaging view always restore correctly after recording?
- Are any drop-down menus, modal dialogs, or active UI edits disrupted?
- Are there microscope states where reading certain attributes raises errors?
- Are there states where the OEM API returns stale, partial, or delayed data?
- What is the typical state-read duration in idle vs. busy microscope states?
- What interval is safe/reasonable for automatic recording during normal use?

### Current known/expected behavior

- Open drop-down menus may close during a state read.
- The recorder attempts to restore the active imaging view after checking all
  quadrants/views.
- If the microscope/OEM API blocks, the background thread may remain busy until
  the API call returns.
- If a recording is already in progress, the next automatic interval is skipped
  rather than starting an overlapping read.
- Pressing stop cancels future scheduled reads but does not forcibly terminate
  an already-running microscope API call.
- If configured, stopping can queue the current draft note and record one final
  state after the current read finishes.

### Future work: state-diff parsing

Each recorded state is verbose. A planned next step is to build tooling to parse
the generated `.yml` files and summarize changes over time.

Potential diff-tool features:

- Load one or more state recorder `.yml` files.
- Compare consecutive recorded states.
- Report only fields that changed.
- Optionally ignore noisy or expected-changing fields, such as timestamps,
  frame counters, elapsed times, live imaging state, or other high-frequency
  telemetry.
- Group differences by subsystem, for example:
  - `beams`
  - `detector`
  - `gas`
  - `patterning`
  - `specimen`
  - `state`
  - `vacuum`
  - `imaging`
- Provide compact human-readable summaries.
- Export diffs to Markdown, CSV, JSON, or a reduced YAML format.
- Support filtering by subsystem or key path.
- Support matching/annotating diffs with user notes saved in the `description`
  field.
- Detect and summarize stage-position changes separately, e.g. changes in
  \(x\), \(y\), \(z\), tilt, and rotation.
- Optionally apply tolerances for floating-point values so tiny numerical noise
  does not produce excessive diff output.

### Possible diff output example

> [!NOTE]
> We may want something more formal for ingestion for an agent, which means we might have to get into ontology

```text
Jul 15, 2026 02:14:03.127 PM -> Jul 15, 2026 02:14:13.115 PM

Description:
Moved to feature A.

Changed fields:
- scope.specimen.stage.current_position.x:
  0.001234 -> 0.001891
- scope.specimen.stage.current_position.y:
  -0.000412 -> -0.000385
- scope.beams.electron_beam.horizontal_field_width.value:
  0.000150 -> 0.000075
- scope.imaging.quad1.active_device:
  Electron -> Ion
```