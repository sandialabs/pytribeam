# Plan: core pytribeam changes from the first hardware test

These changes go in `src/pytribeam` itself, on their own branch, and are merged
back into `mcp` afterwards. They come from the first MCP hardware session
(`src/pytribeam/mcp/TESTING_TAKEAWAYS.txt`), but every one of them is a core
bug or a missing core function: the experiment workflow and the GUI call the
same code and get the same fixes. The MCP server only wraps these functions
(see the MCP plan, `PLAN_MCP.md`, for what it builds on top).

Line numbers are as of commit `5899e13` on `mcp`.

## Before starting: move the enum change to this branch

The `mcp` branch has an uncommitted change to `src/pytribeam/types.py` that
adds `DetectorType.LMABS` (`"LmABS"`), `LMCBS` (`"LmCBS"`) and `STEM3_GMODE`
(`"STEM3_GMode"`), found on the real tool. It is core code: commit it on this
branch, and drop it from `mcp`, so the two branches do not conflict on
`types.py`. It fixes this tool only; C2 makes the code safe for the next
unknown value.

## Summary

| Item | What | Priority | MCP items that wait for it |
|---|---|---|---|
| C1 | Unknown detector values handled without crashing, everywhere | P0 | M2, M3 |
| C2 | `retract_all_devices` restores the detector and fails closed | P0 | M2 |
| C3 | Readback rounding makes current settings invalid (HFW) | P0 | none |
| C4 | `set_detector` that works from any state | P1 | M3 |
| C5 | Detector descriptions table | P2 | M4 |
| C6 | Image focus metric in core | P1 | M8 |
| C7 | Hardware checks to run on the microscope | P1 | none |

Order: C1, then C2 (it relies on C1's restore helper), then C3 and C4 in any
order. C5 to C7 are independent.

---

## C1. Unknown detector values: handle them, safely

**Problem.** Real tools report detector types that `tbt.DetectorType` does not
know (`LmABS` blocked every stage move). Code that converts the microscope's
current or available detector to the enum crashes on such a value, and a
crash part way through a loop that changes the detector leaves it changed.
That is the likely cause of the detector left on External after a failed
move.

Conversions of a value read from the microscope:

- `image.py:183`, `detector_settings_restored`: converts the original
  detector type (and `DetectorMode` on the next line) before the block runs,
  so the restore helper itself fails on an unknown detector, and on any
  detector the probes are run from.
- `image.py:241`, `get_available_detector_types`: converts each available
  type *outside* its `try`, so one unknown value makes the whole probe fail
  instead of being skipped.
- `insertable_devices.py:507`, `retract_all_devices`: converts every
  available detector type.
- `insertable_devices.py:833`, `specimen_current`: converts the initial
  detector it means to restore.
- `factory.py:275`, `active_detector_settings`: converts the current detector.

Conversions of user input (`factory.py:1078`, `factory.py:1997`) are fine: an
unknown value there is a config error and should be refused.

**Change.**

- Where a value is read from the microscope only to be put back, keep the raw
  string and write the raw string back. `detector_settings_restored` should
  store and restore `microscope.detector.type.value` and
  `microscope.detector.mode.value` as strings. It can still yield the enum
  when the value is known; yield `None` (or the string) when it is not, and
  document which.
- Loops over `microscope.detector.type.available_values` iterate the strings,
  and convert only where an enum is required.
- `active_detector_settings` should raise a clear `ValueError` naming the
  unknown detector ("Detector type 'X' is not supported by pytribeam; select a
  supported detector first"), not a bare enum `ValueError`.
- Consider whether `types.DetectorType` should accept unknown values at all
  (an Enum `_missing_` hook). Recommendation: no. A pseudo-member would let
  an unknown detector pass every check silently, which is the wrong default
  for safety decisions (C2). Raw strings at the hardware boundary are enough.

**Done when.** Tests with a stand-in microscope whose `available_values`
include an unknown string (e.g. `"FutureDetector"`):

- `detector_settings_restored` restores an unknown original detector;
- `get_available_detector_types` skips the unknown one and lists the rest;
- `retract_all_devices` does not crash on it (see C2 for what it must do);
- `active_detector_settings` raises a readable `ValueError`.

## C2. `retract_all_devices`: restore the detector, and fail closed

**Problem.** `insertable_devices.retract_all_devices` (line 477) is what every
stage move runs first, in the workflow and in the MCP server. It has three
faults:

1. **It changes the detector and does not put it back.** To check each
   detector, `detector_state` → `detector_insertable` sets
   `microscope.detector.type` to it (line 187). Only the view is restored
   afterwards (line 536), so the electron beam is left on the last detector
   probed (T3 on the test tool), with that detector's brightness and
   contrast. This is why every move changed the imaging detector.
2. **An unknown or unreadable detector counts as safe.**
   `detector_insertable` has a bare `except:` (line 188) that warns
   "Detector will be assumed to not be insertable" and returns `False`, and a
   second `except Exception: return False` when the state cannot be read.
   `detector_state` turns `False` into `STATIONARY`, so the detector is
   skipped and the stage moves. Before a stage move this is the dangerous
   default: an inserted detector that cannot be identified is exactly the one
   that could collide.
3. **A crash part way through leaves whatever detector was being probed.**
   See C1.

**Change.**

- Wrap the detector loop in `image.detector_settings_restored(microscope,
  tbt.Device.ELECTRON_BEAM)` (after C1, it works with any detector), so the
  device, detector type, and mode are put back whether the loop succeeds or
  not. Detector brightness and contrast are per detector on the microscope,
  so restoring the type restores them; confirm this on the tool (C7).
- Split "is this detector insertable" from "what state is it in", and make
  the states explicit:
  - the detector cannot be selected on the electron beam's device: not
    reachable from here, skip it, as now (this is a property of the
    detector, not a failure);
  - it can be selected and reports `Stationary`: fixed, skip;
  - it reports `Retracted`: skip;
  - it reports any other state: retract it (as now), and raise if it does
    not end `Retracted` (as `retract_device` already does);
  - it can be selected but its state cannot be read: **raise**, naming the
    detector, so the move is refused. Do not assume.
- Replace the bare `except:` clauses in this module (lines 188, 449, 563,
  654, 762, 798) with `except Exception` at most, and narrower where the
  AutoScript exception type is known. Bare `except:` also swallows
  `KeyboardInterrupt`.
- Keep `retract_all_devices`'s signature and return value; the workflow
  calls it before every slice.
- `specimen_current` (line 808) has the same shape: it changes the detector
  and HFW and restores them only on success. Its own `TODO` (line 835) already
  proposes the fix: move the restore into `finally`. Do it here, with
  `detector_settings_restored` for the detector.

**Done when.** Stand-in microscope tests show:

- after `retract_all_devices`, the active device, detector type, and mode are
  what they were before, including when one retraction raises;
- a detector whose state read raises makes `retract_all_devices` raise, with
  the detector's name, and nothing moves (`stage.move_to_position` is never
  reached in a workflow-level test);
- a detector that cannot be selected on the device is skipped, as today;
- `specimen_current` restores the detector and HFW when the measurement
  raises.

## C3. Readback rounding makes the current settings invalid

**Problem.** `factory.active_beam_with_settings` rounds what it reads to 6
decimal places (`factory.py:200-208`): voltage, current, HFW and working
distance. On the test tool the HFW maximum was 3.2263976 mm and the current
HFW was at that maximum; rounded, it became 3.226398 mm, which is above the
maximum, so `factory.image` refused the microscope's own current setting.
Every caller that reads the current settings and passes them back through
validation (the MCP imaging tools do exactly this) hits it.

**Change.** Pick one:

- **Recommended:** do not round in `active_beam_with_settings`; it reports
  readings, and the reading is valid by definition. If rounding is wanted
  for display, do it where values are displayed. Check that nothing depends
  on the rounded values (the GUI, `tests/test_factory.py`).
- Or validate with a small relative tolerance at the limits in
  `validate_beam_settings` (`factory.py:1780`), e.g. `1e-6` of the range, and
  clamp to the limit before applying. This also helps a user who types the
  rounded maximum shown in xTUI.

Both are reasonable together; the first is the fix, the second is
robustness.

**Done when.** A test with a stand-in beam whose HFW limit max is 3.2263976
and whose current HFW equals it: `active_image_settings` followed by
`factory.image` with those settings validates.

## C4. `image.set_detector`: works from any state

**Problem.** Recovery needs a way to put the microscope on a known detector
that does not first read anything about the current one. On the test tool the
detector was left on External, and every path that read the current
detector's settings (brightness, through `active_detector_settings`) failed,
so the agent could not get back to a working state.

**Change.** Add to `image.py`:

```python
def set_detector(
    microscope: tbt.Microscope,
    device: tbt.Device,
    detector: tbt.DetectorType,
    mode: Optional[tbt.DetectorMode] = None,
) -> bool:
```

It sets the device (`set_beam_device`), then the type (`detector_type`), then
the mode if given (`detector_mode`), and reads nothing before writing. It
must not insert anything: if the detector is retractable and retracted, it
selects it and leaves it retracted (say so in the docstring; inserting is
`insertable_devices.insert_detector`'s job).

**Done when.** A stand-in microscope whose current detector raises on every
read (`brightness`, `contrast`, `mode`) can be switched to ETD with
`set_detector`.

## C5. Detector descriptions table

**Problem.** In the test the agent only used ETD, never the in-lens or
retractable detectors, because nothing tells it what each one is for. The
GUI has the same gap for new users.

**Change.** Add to `constants.py` a table keyed by `DetectorType`: a one-line
description and typical use (e.g. ETD: Everhart-Thornley, secondary electrons
for topography at longer working distances; TLD/T1/T2/T3: in-lens, high
resolution at short working distance; CBS/ABS: retractable backscatter, Z
and channelling contrast). Insertable or not is **not** in the table; that is
read from the hardware (C2), because it varies by tool.

The descriptions need a microscopist's review; draft them, do not guess
specifics such as which in-lens detector is which signal on this tool.

**Done when.** Every `DetectorType` member has an entry, and a test checks
it (so a newly added member, like `LMABS`, cannot be left out).

## C6. Image focus metric in core

**Problem.** The MCP server computes a `sharpness` score
(`mcp/capabilities/_images.py:112`, the variance of a 3x3 Laplacian divided by
the mean squared intensity). That is image analysis, which belongs in core,
and it is not robust: on noisy SEM frames it is dominated by shot noise, so
in the test it did not track focus and the agent fell back to judging by eye.
The planned autofocus will need a focus metric too, and should use the same
one.

**Change.**

- Add a numpy-only function, e.g. `image.focus_metric(data, bin_px=...)`:
  bin (or Gaussian-blur) first to suppress shot noise, then Laplacian
  variance, normalized by mean intensity as now. Optionally an FFT
  mid-frequency power ratio as a second score. Document that it is only
  comparable between images of the same area at the same settings.
- Choose the binning from pixel noise, not a constant, or expose it; the
  right value depends on dwell time and current.
- Make the MCP server call this (MCP plan, M8) and delete its own copy.
- Do not design autofocus here; that is planned separately. This only
  provides the metric it should share.

**Done when.** On a synthetic test image, blurred by increasing amounts with
noise added, the metric decreases monotonically with blur where the current
Laplacian score does not. Ideally also checked on a saved through-focus
series from the tool.

## C7. Checks to run on the microscope

Behaviour the code cannot settle, to check on the tool once C1 and C2 are in:

- **Brightness and contrast after restoring the detector type.** Does
  selecting a detector type restore its own last brightness and contrast? If
  not, `detector_settings_restored` must save and restore them too.
- **Specimen current with the External detector.** In the test, leaving the
  detector on External changed the specimen current reading from about
  −116 pA to about 0.2 pA. One explanation is that External reroutes the
  specimen current signal, so the reading changed but the beam did not.
  Confirm, because if the beam current itself changed, a failed move had a
  physical side effect.
- **`retract_all_devices` end state.** After a move, the detector, mode,
  brightness and contrast match what they were before.
