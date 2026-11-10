# Plan: MCP server changes from the first hardware test

Changes to the MCP server (`src/pytribeam/mcp`) that follow from the first
hardware session (`TESTING_TAKEAWAYS.txt`). The server is a wrapper on
pytribeam: where a fix belongs in pytribeam itself, it is in the core plan,
`PLAN_CORE.md` (items C1 to C7), on its own branch, and the MCP item here only
uses it. Items marked **waits for Cn** should not start until that core item
is merged into `mcp`.

The README's rules apply to every item: see "How to add a tool" (wrapper,
not reimplementation; honest annotations; every scan time-limited; fail
closed; server-chosen paths; before/after records) and "Testing" (detached,
wrapper, and simulator tests).

## Already done on `mcp` (uncommitted)

- **Tier swap propagated.** Tier 3 is stage movement and tier 4 insertable
  detectors, in `config.py`, `INSTRUCTIONS`, the docstrings, the README, and
  the tests.
- **Reference-frame conventions for the agent** (`docs.py`). The userguide's
  reference-frame page is served as the resource
  `pytribeam://docs/reference-frame` and through the tier 0 tool
  `read_userguide`, and is packaged into the wheel by `force-include`. A short
  summary is in `INSTRUCTIONS`, and the axis directions are in
  `move_to_position`'s docstring.
- **Working rules in `INSTRUCTIONS`**: look harder at saved images before
  taking new ones; resolve the best candidate before surveying; do not
  dismiss features early; ask early when the goal is ambiguous; report
  findings with image and state ids; re-read state after a failed call.
- **To move to the core branch:** the `DetectorType` additions in `types.py`
  (see `PLAN_CORE.md`, "Before starting").

## Summary

| Item | What | Priority | Waits for |
|---|---|---|---|
| M1 | Keep images out of the context | P0 | none |
| M2 | Readable errors for unexpected failures, and a startup self-check | P0 | none |
| M3 | Recover from any detector: `set_detector`, and `prepare_imaging` from any state | P0 | C1, C4 |
| M4 | Failed compound calls restore what they changed | P1 | C1, C2 |
| M5 | Notes that outlive the session | P1 | none |
| M6 | Stage coordinates labelled the same way everywhere | P1 | none |
| M7 | `list_detectors`: what the tool has and what each is for | P2 | C5 |
| M8 | Core focus metric, and a `focus_series` tool until autofocus exists | P2 | C6 |
| M9 | Update the hardware test notes and session checklist | P2 | after the next session |

Deferred, not planned: software rotation/flipping of saved images, a
pixel-to-stage transform with "centre the feature at pixel (x, y)", and
documenting the scan-rotation sign convention. They came from the
character-reading test task, which is not typical SEM work. Revisit if a real
workflow needs them.

---

## M1. Keep images out of the context

**Problem.** The session ran out of context, mostly on images: `/context`
showed about 5.1M tokens for `collect_single_image` and 2.9M for
`view_image`. But the server already returns small previews (768 px by
default, at most 1568), not full frames, so pixel count alone does not explain
those numbers. The backend (Bedrock through LiteLLM) also rejected the
request while the client counted only 238.8k tokens. The likely cause is
payload size: noisy SEM images barely compress as PNG, so one 768x512 preview
is roughly 300 kB, and about 400k characters once base64-encoded. If the
proxy counts that as text, or the backend has a request-size limit, a few
dozen previews are enough.

**Step 1: confirm the cause before changing defaults.**

- From `logs/audit.jsonl` of the test session, list the `preview_px` and
  `max_px` the agent passed, and how many images it requested.
- Measure the encoded size of a few real previews from `images/` at
  768 px, as PNG and as JPEG.
- If possible, check how LiteLLM forwards MCP image content to Bedrock
  (image block, or base64 text).

**Step 2: changes** (in `capabilities/_images.py`, `records.py`,
`imaging.py`):

- Encode previews as JPEG (quality about 85) by default, which is several
  times smaller for noisy images. Keep PNG available
  (`preview_format="png"`) for checks of exact pixel values. The no-stretch
  rule stays: JPEG changes the encoding, not the intensity mapping.
- Lower `collect_single_image`'s default `preview_px` to about 512. The
  `stats` already judge exposure without the picture, and `view_image` with a
  `region` is the way to look closely.
- Report the encoded size (`preview.bytes`) in every result, so the agent and
  the logs can see what each image costs.
- Update the tool docstrings to say so: "Use `stats` to judge exposure; take
  the preview only as large as you need; zoom with `view_image(region=...)`
  rather than a larger preview."

**Client setup, not code** (README, "Agentic usage"): set the client's
auto-compact threshold below the backend's real limit, so compaction runs
while it still can. Document the setting for Claude Code.

**Done when.** Detached tests: the default preview is JPEG and its size is
reported; PNG still works on request; previews are never contrast-stretched
in either format. On the next hardware session, a comparable task finishes
within the context limit.

## M2. Readable errors, and a startup self-check

**Problem.** The first calls of the session, including `ping`, failed with a
bare "Error executing tool". By the error contract in `server.py`
(`_audited`), any exception that is not a `ToolError` reaches the agent only
as a generic failure, with the traceback in `server.log`. The later errors
that named the exception type and message are what made diagnosis possible.

**Change.**

- In `_audited`, turn an unexpected exception into a `ToolError` with
  `f"{type(exc).__name__}: {exc}"` and a note that the full traceback is in
  `server.log`. Keep logging the traceback as now. The message is the
  exception's own text, which may include AutoScript's message; that is
  information the operator's agent needs, and nothing secret is in it
  (bearer tokens are never in exceptions; check `ServerConfig` repr to be
  sure).
- Update the error contract in `server.py`'s docstring and the README to
  match.
- **Startup self-check**, run once in `main` before serving: import pytribeam
  and AutoScript, and if a host is set, connect and read the vacuum state and
  the available detector types. Never fail startup on it. Record the result
  in `server.log`, and report it from `ping` and `get_server_info` as
  `self_check: {ok, checks: [...], errors: [...]}`, so the first call tells
  the agent what is wrong.

**Done when.** A detached test in which a tool raises `RuntimeError("boom")`
shows the agent `RuntimeError: boom`. A detached test with AutoScript
unimportable shows the failure in `get_server_info`'s self-check, and `ping`
still works.

## M3. Recover from any detector

**Waits for C1 and C4.**

**Problem.** After a failed move the detector was left on External, and
`prepare_imaging` could not switch away: `plan()` in `imaging.py` reads the
current settings (`_current`, through `factory.active_image_settings`)
before it applies the requested detector, and reading External's brightness
failed. Recovery depended on the current state being valid.

**Change.**

- New tier 1 tool `set_detector(beam, detector, detector_mode=None)` in
  `views.py`, wrapping core `image.set_detector` (C4). It selects; it never
  inserts (say so). It returns a before/after record like `set_view`.
  Tier 1 because it changes only the detector selection, which the tier 1
  definition already covers. A retractable detector is selected but stays
  retracted; refusing it below tier 4 is unnecessary, since nothing moves.
- In `plan()`, when the agent gives `detector`, select it with
  `set_detector` before `_current()` reads anything, so the merge reads the
  requested detector's settings rather than the broken one's.
- Mention `set_detector` in the error message an unreadable current detector
  produces: "The current detector (External) cannot be read; select a
  supported detector with set_detector."

**Done when.** Detached tests with a fake microscope whose current detector
raises on every read: `set_detector(beam="electron", detector="ETD")`
succeeds, and `prepare_imaging(beam="electron", detector="ETD")` succeeds
without calling `set_detector` first.

## M4. Failed compound calls restore what they changed

**Waits for C1 and C2.**

**Problem.** Failed calls had side effects: a failed move left the detector
on External, and successful moves left it on T3 with different brightness
and contrast. Most of this is `retract_all_devices`, fixed in core (C2), and
`move_to_position` gets the fix with no MCP change.

**Change.**

- `move_to_position`: after C2, add a check rather than a restore. Compare
  the before and after states for imaging settings (detector type, mode,
  brightness, contrast on the electron beam) and add a warning if any
  changed, so a regression is visible at once.
- `prepare_imaging` and `collect_single_image`: if pytribeam raises after it
  started applying settings, put back the settings read at the start of the
  call (the `_current()` values already in `plan()`), through the same
  `_prepare` path. If that fails too, set the fault (the existing fail-closed
  rule). Report in the error which settings were restored.
- No restore after success: an imaging call is meant to change the settings.

**Done when.** Detached tests: a move leaves the imaging settings unchanged
(with a fake `_retract_all` that changes them, the warning appears); an
imaging call whose `_collect` raises restores the earlier detector and
brightness, and a failing restore sets the fault.

## M5. Notes that outlive the session

**Problem.** When the session died, its findings were lost: the audit log
and states record what was done, not what was learned. `INSTRUCTIONS` now
asks the agent to report findings with image and state ids, but they only
live in the conversation.

**Change.** Two tier 0 tools in `records.py` (files only, no hardware lock):

- `record_finding(text, image_ids=[], state_ids=[])`: appends one JSON line
  to `<project_dir>/notes.jsonl` with the time, session id, op id, and the
  given ids (checked to exist). Server-chosen path, as for every file.
  Not `read_only` (it writes a file), not destructive.
- `list_findings(limit=20)`: the most recent notes, oldest first, including
  earlier sessions.

Update `INSTRUCTIONS`: at the start of a session, after
`get_recent_activity`, call `list_findings`; record a finding whenever you
learn something you would need again. Add both tools to the README tier
table and `test_tiers.py`.

Annotation check: the README rule is "`read_only=True` only for tools that
change nothing at all". `record_finding` writes a file, so it is not
read-only, though it is tier 0. Say so in the README next to the rule, as
the exception it is.

**Done when.** Detached tests: findings are appended and listed across two
server instances on the same project directory; unknown image or state ids
are refused; the text is length-limited.

## M6. Stage coordinates labelled the same way everywhere

**Problem.** The agent saw the stage in two systems without noticing: z =
9.91 mm (Specimen, from `get_state`) and Z = 57.25 mm (RAW, from
`get_stage_position`). `INSTRUCTIONS` and the docstrings now say not to mix
them, but the results themselves should make it impossible to miss.

**Change.**

- `get_state`'s condensed view (`state/condense.py`): put the coordinate
  system next to the stage values, with a reminder:
  `stage: {coordinate_system: "Specimen", units: "m, rad", note: "not for
  move_to_position; use get_stage_position"}`. Do not convert to RAW here:
  reading RAW means switching the stage's coordinate system, and `get_state`
  is read-only.
- Every result that includes a position from `_stage_position` already says
  `coordinate_system: "Raw"`; add `units: "mm, deg"` there too.
- The image sidecar (`imaging._write_sidecar`): add `rotation_deg` (scan
  rotation) and `working_dist_mm`, which are not recorded now, so an image
  can be related to the stage later. The stage position is already there.

**Done when.** Detached tests on the condensed state and on a sidecar.

## M7. `list_detectors`

**Waits for C5.**

**Problem.** The agent never tried the in-lens or retractable detectors.
Nothing told it which this tool has or what each is for.

**Change.** A tier 1 tool `list_detectors(beam="electron")` in `hardware.py`
that combines what already exists: the cached
`get_available_detector_types` result, the insertable detectors and their
states, the modes of each (from the cache, probing only what is missing),
and the C5 description of each type. One entry per detector: `type`,
`modes`, `insertable`, `state`, `description`. It probes like the existing
`get_available_*` tools, with the same restore and fault behaviour, and says
so in its docstring. Consider whether the three `get_available_*` tools are
still needed afterwards; keeping them costs little.

**Done when.** Detached test against the fake microscope; simulator test
lists at least ETD with a description.

## M8. Focus

**Waits for C6.** Autofocus itself is planned in core and not designed here.

- Replace `sharpness` in `_images.stats` with core's focus metric (C6), and
  delete the MCP copy. Keep the result key name, or rename it with a note in
  the docstrings that it replaced the old score.
- Until autofocus exists, consider a tier 2 tool
  `focus_series(working_dist_mm: list, region=None, resolution=..., dwell_us=...)`:
  takes one small, fast frame at each working distance through the existing
  `collect_single_image` path (so the time limits, records, and fault rules
  apply to each frame), scores each with the core metric over `region`, and
  returns the curve and the best value, with no previews by default. It
  restores the starting working distance unless told to keep the best.
  Check the whole series against the frame time limit before the first
  frame. When core autofocus lands, the tool either wraps it or is removed.

**Done when.** Detached tests: the series is time-checked up front, each
frame is recorded, the starting working distance is restored on failure;
with fake frames blurred by distance from a chosen focus, the tool finds it.

## M9. Test notes and checklist

- After the next hardware session, replace `TESTING_TAKEAWAYS.txt` with a
  short record of what was fixed where (C and M items), so it does not keep
  describing bugs that are gone. Its section 1 currently says images went
  into the context at full resolution, which is not what the server does
  (see M1).
- Add to the README's "Agent session on the simulator" checklist, and a
  matching hardware checklist:
  - after a stage move, the imaging detector and its settings are unchanged
    (C2, M4);
  - the agent reads `pytribeam://docs/reference-frame` or `read_userguide`
    before its first move, or uses the instructions' summary correctly;
  - previews stay small, and the session's context use is reasonable (M1);
  - a finding recorded in one session is listed in the next (M5).
