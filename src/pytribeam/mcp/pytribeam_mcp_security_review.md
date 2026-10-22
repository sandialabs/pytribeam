# pytribeam MCP branch — Security and Correctness Review

**Reviewed:** `sandialabs/pytribeam`, branch `mcp`  
**Commit:** `6dddc795a4a349d6cbec828c71e061a082dbb337`  
**Date:** 2026-10-22  
**Method:** Static source review; no live-hardware tests performed.

## Summary

The implementation contains several good foundations: server-side capability tiers, a single serialized hardware connection, audit logging, conservative default transport settings, token-gated HTTP access, safe YAML loading, and image identifier validation. However, several trust-boundary and physical-safety concerns should be addressed before enabling unattended or remote microscope control.

The most important issue is that the declared tier model does not consistently correspond to physical side effects. In particular, Tier 1 permits ion-beam imaging and scanning, which can remove material, while the tier description reserves material removal for Tier 4. Tier 0 also includes nominally read-only operations that change microscope UI/device/detector state.

**Review disposition: Changes requested before unattended real-hardware deployment.**

## Findings

### P0 — Tier 1 permits material-removing ion-beam imaging

**Code:** [config.py:46–54](https://github.com/sandialabs/pytribeam/blob/6dddc795a4a349d6cbec828c71e061a082dbb337/src/pytribeam/mcp/config.py#L46-L54), [imaging.py:491–533](https://github.com/sandialabs/pytribeam/blob/6dddc795a4a349d6cbec828c71e061a082dbb337/src/pytribeam/mcp/capabilities/imaging.py#L491-L533), [imaging.py:562–605](https://github.com/sandialabs/pytribeam/blob/6dddc795a4a349d6cbec828c71e061a082dbb337/src/pytribeam/mcp/capabilities/imaging.py#L562-L605)

Tier 1 exposes `prepare_imaging` and `collect_single_image` with `beam="ion"`. The implementation documents that ion imaging sputters material, including through automatic scanning in `prepare_imaging(auto_cb=True)`. Yet configuration describes Tier 4 as material removal. Thus the safety contract expressed by tier names does not reflect exposed capabilities.

**Recommendation:** Explicitly decide whether ion imaging belongs in Tier 1. If material removal is intended to require greater authorization, gate all ion scanning and automatic imaging routines accordingly. Apply dose limits and/or an independent operator-approval control.

### P1 — Tier 0 tools have hardware side effects while marked read-only

**Code:** [hardware.py:223–374](https://github.com/sandialabs/pytribeam/blob/6dddc795a4a349d6cbec828c71e061a082dbb337/src/pytribeam/mcp/capabilities/hardware.py#L223-L374)

The `get_available_*` functions can change active imaging devices, views, or detector settings to probe available capabilities. The stage position and limits functions can set the RAW coordinate system. These functions are registered with the `read_only` MCP annotation. Restoration is attempted but not guaranteed.

**Recommendation:** Separate truly observational operations from active hardware probing. Reclassify probing tools as state-changing and avoid read-only annotations for them. Where possible, derive capability lists from static metadata or passive API reads.

### P1 — Remote HTTP bearer token is transmitted without transport-level encryption

**Code:** [server.py:228–335](https://github.com/sandialabs/pytribeam/blob/6dddc795a4a349d6cbec828c71e061a082dbb337/src/pytribeam/mcp/server.py#L228-L335)

The code uses constant-time bearer-token comparison and refuses HTTP mode without a configured token, both positive controls. But it can bind to non-loopback addresses and directly serves plaintext HTTP. Anyone who intercepts a token on an untrusted network can obtain the server's configured permissions. DNS-rebinding checks and host-header allowlists do not provide encryption.

**Recommendation:** Restrict direct HTTP to loopback. For remote access use an authenticated tunnel, TLS reverse proxy, or HTTPS-capable deployment with appropriate origin/host restrictions. Document that HTTP bearer tokens are not safe on untrusted networks.

### P1 — Single shared credential authorizes every action available on the server

**Code:** [server.py:228–268](https://github.com/sandialabs/pytribeam/blob/6dddc795a4a349d6cbec828c71e061a082dbb337/src/pytribeam/mcp/server.py#L228-L268), [server.py:204–222](https://github.com/sandialabs/pytribeam/blob/6dddc795a4a349d6cbec828c71e061a082dbb337/src/pytribeam/mcp/server.py#L204-L222)

The server's max tier is operator-configured at startup and cannot be raised by a tool, which is useful. However, one bearer token admits every client at that server tier, with no per-principal authorization or per-action operator approval. `confirm_long=True` is an agent-supplied parameter, not independent human authorization.

**Recommendation:** For multiple users or unattended operation, establish client identity and separate role/capability scopes. For dangerous physical actions, approvals should originate from a trusted operator channel and be enforced outside of the LLM's control.

### P1 — Time and exposure guardrails are incomplete

**Code:** [imaging.py:279–299](https://github.com/sandialabs/pytribeam/blob/6dddc795a4a349d6cbec828c71e061a082dbb337/src/pytribeam/mcp/capabilities/imaging.py#L279-L299), [imaging.py:491–560](https://github.com/sandialabs/pytribeam/blob/6dddc795a4a349d6cbec828c71e061a082dbb337/src/pytribeam/mcp/capabilities/imaging.py#L491-L560)

`collect_single_image` checks an estimated frame duration, but `prepare_imaging(auto_cb=True)` can cause scanning without the equivalent duration gate. The estimate is not an independently enforced exposure/dose budget and does not account for cumulative scanning across repeated calls.

**Recommendation:** Apply limits to every scan-producing path, track accumulated sample exposure (especially ion-beam dose), and define maximum scan duration at the instrument control layer.

### P1 — Cancellation and fault recovery are not hardware-enforced

**Code:** [imaging.py:721–763](https://github.com/sandialabs/pytribeam/blob/6dddc795a4a349d6cbec828c71e061a082dbb337/src/pytribeam/mcp/capabilities/imaging.py#L721-L763)

Acquisition runs in a daemon thread and the tool thread waits for completion. This does not enforce a maximum runtime if an AutoScript acquisition hangs, nor establish how process death, network loss, or client disconnect affect physical microscope operation. Client cancellation is not equivalent to stopping hardware.

**Recommendation:** Document and test explicit failure states; introduce a trusted instrument-side timeout/stop path where supported; test disconnected clients, process restarts, SDK hangs, and recovery before accepting another command.

### P2 — State restoration failures do not fail closed

**Code:** [hardware.py:169–213](https://github.com/sandialabs/pytribeam/blob/6dddc795a4a349d6cbec828c71e061a082dbb337/src/pytribeam/mcp/capabilities/hardware.py#L169-L213)

The restoring context manager logs and warns when it cannot restore a view, device, or detector setting. A nominally successful query can therefore leave a changed hardware state. Warnings alone may be too weak where operator state or collision-sensitive detector position is involved.

**Recommendation:** Report restoration success independently. On restoration failure, flag the connection as needing operator reconciliation and block subsequent state-changing calls until cleared.

### P2 — State persistence is atomic per file but not per physical operation

**Code:** [state/__init__.py:41–84](https://github.com/sandialabs/pytribeam/blob/6dddc795a4a349d6cbec828c71e061a082dbb337/src/pytribeam/mcp/state/__init__.py#L41-L84), [imaging.py:634–718](https://github.com/sandialabs/pytribeam/blob/6dddc795a4a349d6cbec828c71e061a082dbb337/src/pytribeam/mcp/capabilities/imaging.py#L634-L718)

Atomic replacement protects each YAML state file, but image acquisitions write multiple independent artifacts (before state, image, after state, sidecar). Crashes or exceptions can leave incomplete records. File-number allocation by scanning the directory is also susceptible to collisions if multiple server processes point to the same project directory.

**Recommendation:** Assign operation IDs; record durable `started`, `completed`, `failed`, and `recovery_required` outcomes; ensure a single process owns an instrument/project directory or use an atomic ID allocator.

### P2 — TIFF loading can exhaust resources

**Code:** [_images.py:35–96](https://github.com/sandialabs/pytribeam/blob/6dddc795a4a349d6cbec828c71e061a082dbb337/src/pytribeam/mcp/capabilities/_images.py#L35-L96)

The preview dimension is capped, but the complete TIFF is decoded and processed first. No explicit pre-decode file-size, pixel-count, or memory budget is enforced. A large/malformed image can use excessive RAM/CPU and interfere with concurrent instrument work.

**Recommendation:** Bound supported image dimensions and decode size, enforce memory/CPU budgets, and use reduced-resolution reads or cached thumbnails where possible.

## Existing strengths

- Default `stdio` transport, Tier 0, and loopback HTTP binding.
- Server-side tool registration by configured tier.
- Bearer-token validation with constant-time comparison and minimum length.
- A shared microscope connection and hardware-operation lock within one process.
- Before/after state captures and structured audit records.
- `yaml.safe_load` and restrictive saved-image identifier matching.

## Suggested prioritization

**Before unattended physical deployment:** Resolve ion-beam tiering, make observational tier semantics accurate, add operator approval for destructive calls, enforce dose/exposure and recovery policies, and protect remote transport.

**Then:** Make restoration failure fail closed; strengthen crash-consistent audit/persistence; enforce image processing budgets; add tests for concurrent clients and instrument/network failures.

## Verification gaps

This is a static code review and should not be read as proof of exploitability or actual microscope damage. Live hardware/AutoScript integration tests, failure-injection tests, deployed network configuration, and validation of instrument interlocks are necessary to determine operational impact. The findings about physical side effects depend on the behavior of the underlying hardware and vendor SDK, although the relevant side effects are acknowledged in the source itself.
