# pytribeam MCP

This describes the usage, structure, and roadmap for MCP development within the `pytribeam` python package.

## Installation

pytribeam includes an MCP server, `pytribeam_mcp`, that lets an AI agent work with the microscope. Which tools the agent can see depends on the configured tier, and the default is tier 0 (read-only). Install it with the `mcp` extra:

```bash
# with pip
pip install "pytribeam[mcp]"

# with uv
uv add "pytribeam[mcp]"

# uv from git clone / repo root folder
uv sync --extra mcp
```

The server is configured through environment variables:

| Variable | Purpose | Default |
|---|---|---|
| `PYTRIBEAM_MCP_MICROSCOPE_HOST` | Host name or IP of the microscope PC | none |
| `PYTRIBEAM_MCP_MICROSCOPE_PORT` | AutoScript port | AutoScript default |
| `PYTRIBEAM_MCP_MAX_TIER` | Highest tier exposed to the agent (0–4, see [Tiers](#tiers)) | `0` |
| `PYTRIBEAM_MCP_PROJECT_DIR` | Folder for this project's logs and saved states | `%LOCALAPPDATA%/pytribeam/mcp` |
| `PYTRIBEAM_MCP_MAX_FRAME_S` | Estimated image time above which the agent must pass `confirm_long` | `300` |
| `PYTRIBEAM_MCP_HARD_MAX_FRAME_S` | Estimated image time above which an image is always refused | `1800` |

Settings can also live in a file of `KEY=VALUE` lines. The server reads
`%LOCALAPPDATA%/pytribeam/mcp.env` if it exists, or the file named by `--env-file`
or `PYTRIBEAM_MCP_ENV_FILE`. Command-line flags and real environment variables
take precedence over the file. It is recommended to create a `.env` file in the project root directory with the above variables for easier management and consistency across different environments.

Everything the server writes goes under the project directory, so pointing it
at an experiment's folder keeps that experiment's record in one place:

```
<project_dir>/
├── logs/
│   ├── server.log       # rotating server log
│   └── audit.jsonl      # one line per tool call
├── states/
│   ├── s0001.yml        # every state the agent reads, saved in full
│   └── ...
└── images/              # written by collect_single_image
    ├── i0001.tif        # the image
    ├── i0001.yml        # its settings, stats, and stage position
    └── ...
```

State ids are the file names and continue across sessions, so the agent can
compare against states from earlier sessions. The GUI state recorder writes the
same format, so pointing it at `<project_dir>/states` adds its recordings to
the same sequence.

## Usage

MCP servers can be connected to an MCP client (such as claude code) or ran in standalone mode permitting manual interactions.

### Manual usage

Manual usage is quite simple and crucial for development and monitoring. To simply test the MCP server and interact with it manually in a browser, run the following (assumes Node.js is installed on your computer):

```bash
npx @modelcontextprotocol/inspector pytribeam_mcp -e PYTRIBEAM_MCP_ENV_FILE="C:\path\to\.env"
```

What this command does is starts a the MCP server using our CLI entrypoint `pytribeam_mcp` and launches a webpage that acts as an inspector for the server. It will open up the web UI to the landing page, where you can connect to the server and peruse the tools, resources, and prompts that we have added to the server.

**This is the primary method of debugging the MCP server. When changes are made, it is important to run the inspector and verify that everything functions properly.**


### Agentic usage

For claude code or codex:

```bash
claude mcp add pytribeam -- pytribeam_mcp
codex mcp add pytribeam -- pytribeam_mcp
```

Images can take minutes, and clients give up on a tool call after their own
timeout. Set it to at least 10 minutes. For Claude Code, set
`MCP_TOOL_TIMEOUT=600000` (milliseconds) in the environment Claude Code runs
in. In the Inspector, raise the request timeout under Configuration (and, if
your version has it, the option to reset the timeout on progress). The server sends progress about
every 5 s while an image acquires.

For other MCP clients, most clients that use a JSON config (Claude Desktop, Cursor, and others) accept this format:

```json
{
    "mcpServers": {
        "pytribeam": {
            "command": "pytribeam_mcp",
            "env": {"PYTRIBEAM_MCP_MICROSCOPE_HOST": "localhost"}
        }
    }
}
```




## Roadmap

The server is built out in stages:

1. **Shared infrastructure** that every later tool depends on. Steps 1.1 and
   1.2 are done. In 1.3, `agent_errors` and `collect_warnings` are done;
   `snapshot`, `acted`, and the generalized `next_path` are left for stage 3,
   which is the first stage to use them.
2. **Tier 0 tools:** diagnostics and hardware queries. Implemented with
   detached tests; the simulator tests (`tests/mcp/test_tier0_simulated.py`)
   and an Inspector pass against the simulator are still to do.
3. **Tier 1 and 2 tools:** imaging, image previews, and handling long
   acquisitions. Implemented with detached tests; the simulator tests
   (`tests/mcp/test_imaging_simulated.py`) and an Inspector pass are still to
   do. Not done from 3.0: marking a call that finished after it was cancelled
   in the audit log.
4. **Tier 3 tools:** stage motion.
5. **Tier 4:** not yet designed.

Read [Conventions](#conventions-for-every-tool) and
[Working on the simulator](#working-on-the-simulator) first; they apply to
every stage. Each step lists what to build, what to watch out for, and what
"done" means.

All development and testing is against the AutoScript **simulator** for now.
Nothing in this roadmap should be run on a physical microscope until it has
been reviewed.

### Target structure

```
src/pytribeam/mcp/
├── __main__.py
├── server.py              # builds the server; CAPABILITY_MODULES allowlist
├── config.py              # ServerConfig, tiers, project directory layout
├── connection.py          # step 1.2: the one shared microscope connection
│
├── state/                 # done: capture, condense, diff (no MCP code)
│
└── capabilities/
    ├── _helpers.py        # step 1.3: error mapping, warnings, snapshots
    ├── diagnostics.py     # tier 0, step 2.1
    ├── state.py           # tier 0, done
    ├── hardware.py        # tier 0, step 2.2
    ├── images.py          # tier 0, step 3.6: list_images, view_image
    ├── _images.py         # step 3.7: previews and image statistics
    ├── imaging.py         # tier 1 (and 2), steps 3.1–3.5
    └── stage.py           # tier 3, stage 4
```

### Tiers

A capability module declares one `TIER`, and the server only loads modules at
or below `PYTRIBEAM_MCP_MAX_TIER`. Tools that need different tiers go in
different modules.

| Tier | Meaning | Modules | Tools |
|---|---|---|---|
| 0 | Observe. Reads the microscope; never changes what it is doing. | `diagnostics`, `state`, `hardware`, `images` | `ping`, `get_server_info`, `check_connection`, `reconnect`, `get_recent_activity`, `get_state`, `compare_states`, `list_states`, `get_available_detector_types`, `get_available_detector_modes`, `get_available_insertable_detectors`, `get_imaging_limits`, `get_stage_position`, `get_stage_limits`, `list_images`, `view_image` |
| 1 | Imaging. Changes beam, detector, and scan settings and acquires images. Can use auto functions (ACB/AF). Only non-insertable detectors allowed. | `imaging` | `set_view`, `prepare_imaging`, `collect_single_image` |
| 2 | Same as Tier 1 except with insertable detectors, which are inserted if needed. | `imaging` (no new tools; see [Stage 3](#stage-3-tier-1-and-2-imaging-tools-capabilitiesimagingpy)) | `prepare_imaging`, `collect_single_image` |
| 3 | Stage motion. | `stage` | `move_to_position` |
| 4 | Material removal and other high-risk operations. | `TBD` | `TBD` |

### How to add a tool

All tools go in the `capabilities/` directory, in a module corresponding to their tier and functionality. At a high level, each module should declare its `TIER` and provide a `register(add, config, connection)` function that the server calls to register the tools. In its simplest form, this looks like:

```python
# Example capability module at tier 0.
TIER = 0

# Register the tools provided by this module.
def register(add, config, connection):
    """Register the tools provided by this module."""

    # Define a simple hello world tool.
    def hello_world() -> str:
        """A simple hello world tool."""
        return "Hello, world!"

    # Register the tool with the server.
    add(hello_world)
```

Tools that need the microscope use the shared connection, which connects on first use, takes the lock, and sends stdout to stderr for the duration:

```python
with connection.use() as microscope, agent_errors():
    return _stage_position(microscope)
```

Put each pytribeam call in a small module-level function that imports pytribeam itself (see `capabilities/hardware.py`). The server then starts without AutoScript, and detached tests can replace that one function with a fake.

A few implementation notes:

- All tools should handle errors gracefully and follow the error contract specified in `server.py`. Error messages are sent directly to the agent, so they should be written to be informative and user-friendly.
- Avoid writing to stdout directly; use the connection context manager to redirect output to stderr. Stdout carries the MCP protocol, and a single stray `print` can corrupt the session.
- Always import pytribeam modules inside the functions that need them to ensure the server can start without AutoScript.
- pytribeam reports useful information through `warnings.warn` that should be recorded and returned as part of the tool result (step 1.3 helper).
- Always clean up resources, such as file handles and microscope connections, to avoid leaving the system in an inconsistent state.
- Always validate inputs and handle edge cases to prevent unexpected behavior and maintain system stability.
- Use flat, simple data structures for communication with the agent (inputs, results), avoiding nested objects and complex types. Put units in the argument names. `None` should mean "leave this setting as it is".
- Docstrings should be clear and concise, describing the tool's purpose, side effects, units, and what a refusal means. Avoid NumPy-style parameter sections; the schema already lists the arguments.
- Pass `read_only=True` for tier 0 tools and `destructive=True` for anything that can damage the sample or hardware.



9. **Files.** The server chooses every file path, under the project directory
   (`config.project_dir`). Never accept a path from the agent: a tool that
   writes to an agent-chosen path can overwrite anything. Name files the same
   way as states: a letter prefix and a 4-digit counter (`i0001.tif`).
10. **Every action leaves a record.** Tools at tier 1 and above take a state
    snapshot before and after acting, and return both state ids and the diff
    (step 1.3 helper). The agent sees exactly what its action changed, and the
    project folder keeps the before/after states next to the audit log.

### Testing
Every step needs three kinds of check:
- **Detached tests** in `tests/mcp/`, marked `@pytest.mark.detached`, that drive the tools through an in-process MCP `Client` with a fake microscope. `tests/mcp/test_state_capabilities.py` is the template. They cover argument validation, refusals, and result shape.
- **Simulator tests**, marked `@pytest.mark.simulated`, that call the same tools against the real simulator through `build_server`.
- **A manual pass in the MCP Inspector** (see [Manual usage](#manual-usage)): call each new tool once against the simulator and check its result.

### Python environment

- The MCP server needs Python 3.10 or 3.11 (`mcp` requires ≥3.10; pytribeam requires ≤3.11.14). Create the environment with `uv sync --extra mcp` on the simulator PC.
- Run the server on the simulator PC with `PYTRIBEAM_MCP_MICROSCOPE_HOST=localhost` and a project directory of your own, e.g. `PYTRIBEAM_MCP_PROJECT_DIR=C:\Users\you\mcp_dev`. Put both in a `.env` file and pass it with `--env-file`.
- `@pytest.mark.simulated` tests only run on machines listed in `Constants.offline_machines` (`src/pytribeam/constants.py`). If yours is not listed, add the simulator PC's hostname there.
- On a machine without the `mcp` package, the MCP tests can run in a temporary environment:
  `PYTHONPATH=src uv run --no-project --python 3.11 --with "mcp>=2.2,<3" --with pytest --with anyio --with pyyaml --with pillow --with numpy python -m pytest tests/mcp -o addopts=""`


### Stage 1: Shared infrastructure

#### 1.1 Tier scheme and configuration

- `config.py`:
  - Set `MAX_TIER = 4`.
  - Rewrite the "Tiers" section of the module docstring to match the
    [Tiers](#tiers) table above. It currently says tier 2 is
    acquisition/motion and tier 3 is material removal.
  - Add an `images_dir` property (`project_dir / "images"`) next to
    `states_dir`.
- `server.py`: update `INSTRUCTIONS` with one sentence explaining the tiers, so
  the agent knows to ask the user to raise the tier rather than look for a way
  around a refusal.
- **Done when** `ServerConfig(max_tier=4)` is valid, `max_tier=5` raises, and
  the existing tests pass.

#### 1.2 Shared microscope connection

At present `capabilities/state.py` holds its own connection. Every hardware
module needs the same one, so move it into `src/pytribeam/mcp/connection.py`.

- Create a `MicroscopeConnection` class, constructed with the config. It:
  - connects lazily on first use, with `utilities.connect_microscope(...,
    quiet_output=True)` (move `_connect` from `capabilities/state.py`);
  - holds a `threading.Lock`.
- `use()` is a context manager that:
  1. takes the lock;
  2. redirects stdout to stderr;
  3. connects if needed, raising `ToolError` with the host in the message if
     the connection fails;
  4. yields the microscope;
  5. drops the connection if a `ConnectionError` escapes, so the next call
     reconnects.

  It must be safe to call re-entrantly from the same tool, so use an
  `RLock`.
- Also give it:
  - `connected` (property, never connects);
  - `reset()` (drop the connection);
  - `cache`, a dict cleared by `reset()`, for per-connection results such as
    the detector lists in step 2.2.
- `server.py`:
  - `build_server` creates one `MicroscopeConnection(config)` and passes it to
    every module as `register(add, config, connection)`.
  - Update `diagnostics.py`, `state.py`, and the fake modules in
    `tests/mcp/test_server.py` to the new signature.
- `capabilities/state.py`: replace its private connection code with
  `connection.use()`. Its tests should only need the fakes moved to the
  connection.
- **Done when** all `tests/mcp` tests pass, and a new detached test shows that
  two tools from different modules use one connection: one connect call
  between them.

#### 1.3 Shared helpers (`capabilities/_helpers.py`)

- `agent_errors()`: a context manager that converts `ValueError`,
  `SystemError`, and `NotImplementedError` raised inside it into `ToolError`
  with the same message. Leaves `ToolError` alone; lets everything else
  propagate.
- `collect_warnings()`: a context manager around
  `warnings.catch_warnings(record=True)` that yields a list. Each warning's
  message is whitespace-collapsed, because pytribeam uses multi-line
  f-strings.
- `snapshot(connection, states_dir, description)`: captures and saves a state
  exactly as `get_state` does, returning `(state_id, state)`. Refactor
  `capabilities/state.py` so `get_state` and this helper share one
  implementation.
- `acted(before, after)`: builds the standard record for an action, i.e.
  `{"before_state_id", "after_state_id", "changes"}`, where `changes` is
  `diff(...)["changed"]`.
- Generalize `pytribeam.mcp.state.next_path(directory)` to
  `next_path(directory, prefix="s", suffix=".yml")` so images can use
  `next_path(images_dir, "i", ".tif")`. Keep the default behavior identical.
- **Before relying on snapshots,** time `get_state` on the simulator. If a
  capture takes more than about 3 s, make snapshots optional rather than
  part of every action.
- **Done when** each helper has a detached unit test.

### Stage 2: Tier 0 tools

#### 2.1 Diagnostics (`capabilities/diagnostics.py`)

| Tool | Returns | Notes |
|---|---|---|
| `ping(message)` | exists | Leave as is. |
| `get_server_info()` | pytribeam and AutoScript versions, Python version, `max_tier`, the tier table with which tiers are enabled, `project_dir`/`log_dir`/`states_dir`/`images_dir`, microscope host and port, `connected` | Must not connect or import AutoScript: take the AutoScript version from `pytribeam._package_metadata.get_autoscript_version()`, and `connected` from `connection.connected`. |
| `check_connection()` | `connected`, host, port, `simulator`, round-trip time in ms of one cheap read (`microscope.vacuum.chamber_state`), vacuum state, active view and device | Connects if needed. On failure, **return** `connected: false` and the error message instead of raising: reporting the problem is the job of this tool. `simulator` is true when this machine's hostname is in `Constants.offline_machines`. |
| `reconnect()` | same as `check_connection` | `connection.reset()`, then `check_connection()`. Use it after the microscope software restarts. |
| `get_recent_activity(limit=20)` | The last `limit` records from `<log_dir>/audit.jsonl`, newest last | Reads the file directly; no hardware. Lets the agent recover what happened in earlier sessions. Cap `limit` at 200. |

**Done when** each tool has a detached test (fake connection) and has been
called in the Inspector against the simulator.

#### 2.2 Hardware queries (`capabilities/hardware.py`)

These answer "what can this microscope do, and where is it?" before the agent
asks a tier 1 or tier 3 tool to act.

**`get_available_*` tools**

| Tool | Wraps | Returns |
|---|---|---|
| `get_available_detector_types(beam="electron")` | `image.get_available_detector_types(microscope, device)` | `{"beam", "detector_types": [str]}` |
| `get_available_detector_modes(beam="electron", detector=None)` | `image.get_available_detector_modes(microscope, device, detector)` | `{"beam", "detector", "modes": [str]}` |
| `get_available_insertable_detectors()` | `image.get_available_insertable_detector_states(microscope)` | `{"detectors": [{"detector": str, "state": str}]}` |

Notes:

- `beam` is `Literal["electron", "ion"]`, mapped to `tbt.Device.ELECTRON_BEAM`
  or `tbt.Device.ION_BEAM`. `detector` is a `tbt.DetectorType` value such as
  `"ETD"`.
- One tool covers both insertable-detector functions. The `_states` variant
  returns everything the plain one does, plus each detector's state.
- **These are not passive reads.** To find out what works, they switch the
  active quadrant's device and try every detector type in turn, then switch
  back. On a microscope in use, the operator will see their screen change for
  a few seconds. So:
  - Say so in each docstring.
  - Cache results in `connection.cache`. The hardware does not change during a
    session, so call each underlying function at most once per beam/detector
    combination, until `reconnect()`.
  - The pytribeam functions restore the device and detector only if nothing
    fails, because they don't use `try`/`finally`. Record the active view,
    device, detector type, and mode yourself before calling, and restore them
    in a `finally` block.
  - The functions return enum members, and tuples in the insertable case.
    Convert them to strings.
  - `get_available_detector_modes` returns `None` and warns when the detector
    is not valid for that beam. Turn that into a `ToolError` that lists the
    valid detector types.
  - `get_available_insertable_*` always switch to the electron beam: insertable
    detectors are only reachable from the electron beam.

**Limits and stage tools**

| Tool | Wraps | Returns |
|---|---|---|
| `get_imaging_limits(beam="electron")` | `factory.beam_limits`, `factory.scan_limits` (both take the AutoScript beam object from `utilities.beam_type(beam, microscope)`) | Min and max of `voltage_kv`, `current_na`, `hfw_mm`, `working_dist_mm`, `rotation_deg`, `dwell_us`. The preset resolutions (`tbt.PresetResolution`) as `"WIDTHxHEIGHT"` strings. For the ion beam, the discrete current steps in nA (from `beams.ion_beam.beam_current.available_values`). |
| `get_stage_position()` | `factory.active_stage_position_settings` | `x_mm, y_mm, z_mm, r_deg, t_deg` and `coordinate_system`. Note: this sets the stage's default coordinate system to RAW as a side effect, which later `get_state` captures will show. |
| `get_stage_limits()` | `factory.stage_limits` | min and max per axis, in mm or degrees |

- `get_imaging_limits` lets the agent pick valid values before calling a tier 1
  tool. Report them in the tier 1 argument units.
- `get_stage_position` reports in **RAW** coordinates, the system
  `move_to_position` uses. `get_state` reports the stage in whatever
  coordinate system is current (the fixtures show `Specimen`) and in meters,
  so the agent must not feed those values into a move. Say this in both
  docstrings.

**Done when** each tool has detached tests (including the restore-on-failure
path), a simulator test, and has been run once in the Inspector.

### Stage 3: Tier 1 and 2 imaging tools (`capabilities/imaging.py`)

All imaging tools live in one module at `TIER = 1`. Tier 2 does not add tools;
it lifts the detector-insertion guardrail on the tier 1 tools (step 3.3). Read
the tier with `config.max_tier` inside the tool. This is the one exception to
"one module, one tier"; the alternative is two copies of every imaging tool.

#### 3.0 Long calls

A high-resolution frame with a long dwell takes minutes. The SDK runs sync
tools in a worker thread, so the server stays responsive, but every tool call
currently waits on `_TOOL_LOCK` for at most 60 s. Fix that before adding any
tool that can run long:

- **Only hardware tools take the lock.** Add `uses_microscope: bool = True` to
  `add(...)` and skip `_TOOL_LOCK` when it is false. Pass
  `uses_microscope=False` for `ping`, `get_server_info`,
  `get_recent_activity`, `list_states`, `list_images`, and `view_image`, so the
  agent can still look around while an image is acquiring. `compare_states`
  without `after` reads the microscope and keeps the lock.
- **Say what the server is busy with.** While a tool holds the lock, record its
  name, its start time, and its expected duration if it gave one (3.4). A call
  that cannot get the lock waits only while the running call is expected to
  finish within `BUSY_GRACE_S` (15 s), so parallel quick reads queue instead
  of failing. Otherwise it fails at once with e.g. "collect_single_image has
  been running for 12 s, about 140 s left". Waiting quietly for minutes is
  worse: the client may time out with no explanation.
  *As built:* the lock lives on the shared `MicroscopeConnection`
  (`hold()`, `expect()`, `busy`), and `get_server_info` reports `busy`.
- **Cancellation only stops the client waiting.** If the user cancels, the
  client stops waiting, but the worker thread finishes the scan and saves the
  image, and the lock is held until then. This is deliberate for now; calling
  `stop_acquisition` on cancel can come later if clients start reporting
  cancellation reliably. Put a sentence on this in the docstring of every tool
  that can run long, and log a completed-after-cancel call in the audit record
  (`"cancelled": true`) if the SDK reports it.
- **Client timeouts.** Clients set their own tool timeout (Claude Code:
  `MCP_TOOL_TIMEOUT`; the Inspector's request-timeout setting). List both under
  [Agentic usage](#agentic-usage) with a recommended value of at least 10 min.
- **Done when** a detached test holds a slow fake hardware tool in one task
  and shows that `get_server_info` answers meanwhile and that a second hardware
  tool is refused at once with the running tool's name.

#### 3.1 `set_view`

- Signature: `set_view(quad: Literal[1, 2, 3, 4]) -> dict`. Wraps
  `image.set_view(microscope, tbt.ViewQuad(quad))`.
- Returns the new `active_view` and `active_device`, read back from the
  microscope. `image.set_view` itself returns `None` despite its docstring.
- Docstring:
  - Quads are 1 = upper left, 2 = upper right, 3 = lower left, 4 = lower
    right.
  - By pytribeam convention the electron beam is in quad 1 and the ion beam
    in quad 2.
  - Detector settings in the state belong to whichever quad is active, so
    they will change when the view changes.
- Snapshot before and after (convention 10). Not destructive.

#### 3.2 Shared helpers (rest of step 1.3)

Finish the helpers left over from step 1.3, which imaging is the first to use:

- `snapshot(connection, states_dir, description)` and `acted(before, after)`.
  Time `get_state` on the simulator first; if a capture takes more than about
  3 s, make snapshots optional (`record_states: bool = True`) rather than
  adding that to every image.
- `next_path(directory, prefix="s", suffix=".yml")`, with today's behavior as
  the default.

#### 3.3 `prepare_imaging`

**Signature**

```python
def prepare_imaging(
    beam: Literal["electron", "ion"],
    voltage_kv: Optional[float] = None,
    current_na: Optional[float] = None,
    hfw_mm: Optional[float] = None,
    working_dist_mm: Optional[float] = None,
    dynamic_focus: Optional[bool] = None,     # electron only
    tilt_correction: Optional[bool] = None,   # electron only
    detector: Optional[str] = None,           # tbt.DetectorType value, e.g. "ETD"
    detector_mode: Optional[str] = None,      # tbt.DetectorMode value
    brightness: Optional[float] = None,       # 0 to 1
    contrast: Optional[float] = None,         # 0 to 1
    auto_cb: bool = False,                    # auto contrast/brightness
    rotation_deg: Optional[float] = None,
    dwell_us: Optional[float] = None,
    resolution: Optional[str] = None,         # "WIDTHxHEIGHT", e.g. "1536x1024"
) -> dict:
```

**Implementation, in order**

1. Switch to the beam's default quad and device. Build the beam with
   `tbt.ElectronBeam(settings=tbt.BeamSettings())` (or `IonBeam`); its
   `default_view` and `device` are what `image.set_view` and
   `image.set_beam_device` need.
   `factory.active_image_settings` reads the *active* device and raises if it
   is a camera, and detector settings are per-quad, so this has to come first.
2. Read the current settings with `factory.active_image_settings(microscope)`.
3. Build a settings dict in the same format as an `image` step of an
   experiment config. `tests/mcp/state_records/steps.yml` has complete
   examples.
   - Start from the current settings, then overwrite each field the agent
     passed.
   - Every field must end up filled in. In particular, fill
     `dynamic_focus` and `tilt_correction` from the current values:
     `image.beam_angular_correction` treats `None` as "turn off".
   - `auto_cb=True` fills the `auto_cb` sub-dictionary with the full frame
     (`left: 0, top: 0, width: 1, height: 1`) and leaves `brightness` and
     `contrast` unset. Refuse `auto_cb` together with `brightness` or
     `contrast`; `factory.image` rejects that too, but with a message written
     for YAML authors.
   - Use `step_general: {step_type: image, ...}` as in the example.
4. Validate by calling `factory.image(microscope, step_settings,
   step_name="mcp", yml_format=tbt.YMLFormatVersion.V_1_0)`. This reuses all
   the range and schema checks the experiment workflow already has. Convert
   its `KeyError`, `ValueError`, and `NotImplementedError` into `ToolError`.
5. Apply the guardrails (below).
6. Call `image.prepare_imaging(settings)`. Then, if `resolution` was given and
   is a preset, call `image.beam_scan_resolution(...)`: `prepare_imaging`
   does not set the resolution.
7. Return the applied settings (re-read with
   `factory.active_image_settings`), `estimated_frame_s` (3.4), `warnings`,
   and the before/after record. With `auto_cb`, the re-read brightness and
   contrast are the values the auto function chose.

**Guardrails.** Refuse with a `ToolError` instead of letting
`prepare_imaging` do these, because they go beyond changing imaging
parameters:

- **Turning a beam on.** `image.beam_ready` turns the beam on if it is off.
  If `beams.<beam>.is_on` is false, refuse: "The ion beam is off; ask the
  operator to turn it on." Unblanking is allowed.
- **Inserting a detector (tier 1 only).** `image.imaging_detector` inserts a
  retractable detector if it is not already inserted. Check with
  `devices.detector_state`:
  - `STATIONARY`: allowed at tier 1.
  - Any retractable detector: refused at tier 1, even if it is already
    inserted, with "<detector> is retractable; using it needs tier 2."
  - At tier 2 and above, allowed; pytribeam inserts it if needed. The result
    says `detector_inserted: true` when that happened (state before was not
    `INSERTED`). The tool does not retract it afterwards; retracting is left
    to the operator or a later tier 4 tool.
- **Vacuum.** `beam_ready` already raises if the chamber is not pumped. Make
  sure its message reaches the agent.

**Other side effects to put in the docstring**

- Changing voltage or current waits about 5 s each.
- For the electron beam, angular correction is set to Automatic and scan
  rotation is set to 0 first. `factory.image` rejects a nonzero rotation
  together with dynamic focus or tilt correction.
- Ion beam currents are discrete. Pick a value from `get_imaging_limits`.
  A value off the list is matched within 5% or refused.
- `auto_cb` scans the sample to choose brightness and contrast. With the ion
  beam that removes material (see 3.5).
- At tier 2, a retractable detector may be inserted (physical motion).

**Done when**

- Detached tests cover:
  - only-overrides-are-changed;
  - each guardrail, including tier 1 refusing and tier 2 allowing a
    retractable detector;
  - `auto_cb` together with `brightness`/`contrast` refused;
  - invalid detector and resolution messages;
  - `dynamic_focus`/`tilt_correction` preserved when not passed.
- A simulator test changes HFW and dwell time and the after-state shows
  exactly those changes.

#### 3.4 Acquisition time

- **Estimate before scanning.** `estimated_frame_s = width * height *
  dwell_us * 1e-6`, plus a fixed overhead of about 1 s for line flyback and
  setup. Calibrate the overhead on the simulator by timing a few frames, and
  report the real time (`acquisition_s`) in the result so it can be checked
  against the estimate later.
- **A configured maximum.** Add `PYTRIBEAM_MCP_MAX_FRAME_S` (default 300) to
  `ServerConfig`. Refuse a frame whose estimate is longer, unless the call
  passes `confirm_long: bool = True`. The refusal gives the estimate and
  suggests a shorter dwell or smaller resolution, so a 20-minute frame never
  starts by accident. A second limit, `PYTRIBEAM_MCP_HARD_MAX_FRAME_S`
  (default 1800), cannot be overridden by the agent at all.
- **Progress.** Take a `ctx: Context` argument (the SDK injects it and it does
  not appear in the schema) and call `ctx.report_progress(elapsed, estimate,
  message)` about every 5 s while the frame is acquiring, from a small
  background thread using `anyio.from_thread.run`. Clients that support it
  show a progress bar, and some reset their timeout on each notification.
  Progress must never fail the tool: catch and log any error from reporting it.
  Check that `ctx` passes through `_audited`'s `functools.wraps` wrapper; if
  the SDK cannot find it, the wrapper has to declare it explicitly.
- **Done when** a detached test shows the refusal above the limit, the
  `confirm_long` override, the hard limit, and that progress notifications
  arrive at a client during a slow fake acquisition.

#### 3.5 `collect_single_image`

- **Signature.** The same arguments as `prepare_imaging`, plus
  `bit_depth: Literal[8, 16] = 8`, `description: str = ""`,
  `confirm_long: bool = False`, `preview: bool = True`, and
  `preview_px: int = 768`.
- **Implementation.**
  - Build and validate the settings exactly as in step 3.3, sharing the code; don't
    copy it.
  - Check the acquisition time (3.4) before anything moves or scans.
  - Save to `next_path(config.images_dir, "i", ".tif")`.
  - Apply the settings as in 3.3, then grab with
    `image.grab_preset_resolution_frame` or `image.grab_custom_resolution_frame`.
    *As built:* this does not call `image.collect_single_image`, which would
    run `prepare_imaging` a second time: another ~5 s of voltage and current
    checks, and with `auto_cb`, a second auto contrast/brightness scan, which
    removes material with the ion beam.
  - Preset resolutions grab in memory and save with metadata. Any other
    resolution is written by AutoScript straight to disk and is forced to
    8-bit; turn that warning into a `warnings` entry.
  - Write a sidecar `i0001.yml` next to the image (3.6) after the image is
    saved. If the call fails, write neither.
- **Annotate `destructive=True`.** Ion-beam imaging sputters the surface it
  scans, so every ion image removes some material. The docstring must say so
  and recommend the electron beam unless the ion beam is needed. *Open
  question: ion imaging may belong in a higher tier.*
- **Returns** a list: the result dict as JSON text, then (if `preview`) the
  preview as MCP image content via the SDK's `Image(data=..., format="png")`.
  The dict holds:
  - `image_id` (the file stem), `path`;
  - `beam`, `detector`, `detector_mode`, `resolution`, `bit_depth`,
    `dwell_us`, `hfw_mm`;
  - `pixel_size_nm` (`hfw_mm * 1e6 / width`);
  - `estimated_frame_s`, `acquisition_s`;
  - `stats` (3.7);
  - `preview` (`{"width", "height", "scale"}`, or null);
  - `detector_inserted` (tier 2 only);
  - `dynamic_focus`, `tilt_correction` as left after imaging;
  - `description`, `warnings`, and the before/after record.
- **Leave angular correction as it is after imaging.** The experiment
  workflow (`image.image_operation`) turns dynamic focus and tilt correction
  off after each image; this tool should not. Report the final values in the
  result instead.
- **Done when** detached tests cover file naming, the result shape with and
  without a preview, and that a failed acquisition leaves no image or sidecar;
  and a simulator test produces `images/i0001.tif` and `i0002.tif` in a
  temporary project directory, both readable, each with a sidecar.

#### 3.6 Image records: `list_images` and `view_image`

These are tier 0 tools in a new `capabilities/images.py`: they only read files
the server wrote, never the microscope, and take no hardware lock (3.0).

- **Sidecar.** `<image_id>.yml` next to each image, written by
  `collect_single_image`: the returned dict minus `warnings` and the preview,
  plus `recorded_at` and the stage position in RAW mm/deg
  (`get_stage_position`'s format) at the time of the image. It is what
  `list_images` reads, so TIFFs are never parsed for metadata. An image without
  a sidecar (e.g. copied in by hand) is listed with only its id and size.
- **`list_images(limit=20)`**: oldest first, newest last, like `list_states`.
  Each entry has `image_id`, `recorded_at`, `description`, `beam`, `detector`,
  `resolution`, `hfw_mm`, `pixel_size_nm`, the stage position, and the
  before/after state ids. `total` is how many exist.
- **`view_image(image_id, region=None, max_px=1024, grid=False)`**: re-reads a
  saved image and returns it like `collect_single_image` does, a dict then
  image content. Use it to look at an earlier image again or to zoom in.
  - `region` is `{"left", "top", "width", "height"}` as fractions 0–1 of the
    full image, the same convention as pytribeam's `ScanArea`. Crop at full
    resolution first, then downsample to `max_px`, so a small region is seen at
    up to full detail without taking a new image.
  - Cap `max_px` at 1568 (the long edge Claude uses without rescaling) and
    refuse a region smaller than 16 px on a side.
  - `grid=True` draws a labelled grid (columns A, B, ..., rows 1, 2, ...) over
    the preview and returns each cell's bounds in full-image pixels, so the
    agent can refer to "the particle in C4". The grid is drawn on the preview
    only, never on the saved image.
  - `image_id` must match `^i\d+$` and exist, like state ids; never build a
    path from anything else.
- **Done when** detached tests cover listing order and `limit`, a missing
  sidecar, crop coordinates, the `max_px` cap, the grid cell bounds, and
  malformed ids, using small synthetic TIFFs written in the test.

#### 3.7 Previews and image statistics

Shared code in `capabilities/_images.py`, used by `collect_single_image` and
`view_image`. It needs only numpy and Pillow (already dependencies), so it is
fully testable without AutoScript.

- **Preview.** Downsample so the long edge is at most `preview_px` (default
  768, about 800 image tokens at Claude's rate of roughly width × height / 750;
  1024 px is about 1,400). Encode as 8-bit grayscale PNG.
- **No auto-stretch.** Convert 16-bit images to 8 bits by a fixed linear
  shift (`>> 8`), never by stretching each image to fill the range. A
  stretched preview would hide exactly the problems the agent is looking for:
  a dark, washed-out, or clipped image would look fine. State the mapping in
  `preview.mapping`.
- **Statistics** (`stats`), computed on the full-resolution image, not the
  preview, in the image's own bit depth:
  - `min`, `max`, `mean`, `std`, and the 1st, 50th and 99th percentiles;
  - `clipped_low_frac` and `clipped_high_frac`: fractions of pixels at the
    lowest and highest possible value;
  - `sharpness`: variance of a 3×3 Laplacian, normalized by the image's mean
    squared intensity, so it compares across brightness. It is only
    meaningful relative to other images of the same area at the same settings;
    say so in the docstring.
- **Docstring guidance for the agent:** use the preview to see what is in the
  image, and the statistics to judge brightness, contrast, and focus. E.g.
  `clipped_high_frac > 0.01` means lower the contrast or brightness; when
  focusing, compare `sharpness` across images.
- **Done when** unit tests cover 8- and 16-bit inputs, the fixed mapping
  (a dark 16-bit image stays dark), clipping fractions, sharpness rising for a
  sharper synthetic image, and the downsampled size.

#### Tools added in stage 3

| Tool | Module | Tier | Lock |
|---|---|---|---|
| `set_view` | `imaging` | 1 | yes |
| `prepare_imaging` | `imaging` | 1 (retractable detectors at 2) | yes |
| `collect_single_image` | `imaging` | 1 (retractable detectors at 2) | yes |
| `list_images` | `images` | 0 | no |
| `view_image` | `images` | 0 | no |

Not in this stage: autofocus (needs a direct AutoScript call, since pytribeam
has no wrapper, and its behavior on the simulator checked first), stopping a
scan on cancel, and moving to a point picked in an image (tier 3, after
stage 4).

### Stage 4: Tier 3 stage motion (`capabilities/stage.py`)

#### 4.1 `move_to_position`

**Signature**

```python
def move_to_position(
    x_mm: Optional[float] = None,
    y_mm: Optional[float] = None,
    z_mm: Optional[float] = None,
    r_deg: Optional[float] = None,
    t_deg: Optional[float] = None,
) -> dict:
```

All values are in the **RAW** coordinate system, the same one
`get_stage_position` reports. `None` keeps an axis where it is. At least one
axis must be given.

**Implementation**

1. Read the current position with `factory.active_stage_position_settings`.
   Fill in any `None` axes from it and build a `tbt.StagePositionUser`.
2. Run the safety checks below. Refuse on any failure.
3. Call `stage.move_to_position(microscope, target)` with the default
   tolerance (`Constants.default_stage_tolerance`).
4. Return the position before and after (mm/deg), the elapsed time, warnings,
   and the before/after state record.

**Safety checks before moving**

- **Limits.** `stage.move_to_position` already refuses targets outside the
  stage limits by raising `ValueError`. Make sure the message, which includes
  the limits, reaches the agent.
- **Inserted detectors.** Refuse if any insertable detector is not
  `RETRACTED`. Use the step 2.2 insertable-detector query, without the cache, since
  states change.
- **Manipulator.** Refuse if `microscope.specimen.manipulator.state` is not
  `Retracted`.
- **Bulk stage.** Refuse if the bulk stage is not active (the compustage is
  in): reading `specimen.stage.current_position` raises, as in
  `tests/mcp/state_records/s0009.yml`.
- Do not retract anything automatically. Retracting is itself motion. Tell
  the agent what is in the way so it can ask the operator.

**What `stage.move_to_position` does, for the docstring**

- Switches quad 4 to the CCD camera during the move, then pauses it and
  restores the view.
- Sets the default coordinate system to RAW.
- Moves axes one at a time in the order R, X, Y, Z, T. Before a rotation, it
  first returns the tilt to 0° to reduce collision risk.
- Checks the final position and retries once.
- A move that still misses raises `SystemError` with the per-axis error.
  Convert it to a `ToolError` that tells the agent to stop and report to the
  operator rather than retry.

**Other requirements**

- Annotate `destructive=True`.
- **Never expose `stage.stop()`.** It disconnects the microscope and raises.
  An emergency-stop tool needs its own design.
- **Done when**
  - Detached tests cover partial-axis targets, each refusal, and the
    `SystemError` path.
  - A simulator test moves X and Y and back, and `compare_states` shows only
    the stage axes changing.

### Stage 5: Tier 4 (TODO)

Not yet designed. Candidates from the existing pytribeam modules, each of
which needs its own safety review before it is added:

- FIB milling: `fib.mill_operation`
- laser milling: `laser.laser_operation`
- EBSD and EDS mapping: `laser.map_ebsd`, `laser.map_eds`
- detector insertion and retraction: `insertable_devices`
- turning beams on and off

Tier 2 is unassigned. Some of these may belong there instead.
