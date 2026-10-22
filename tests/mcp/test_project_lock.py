"""One server process per project directory. No AutoScript."""

## python standard libraries
import json
import subprocess
import sys
import textwrap

# 3rd party libraries
import pytest

# local libraries
from pytribeam.mcp import project_lock

pytestmark = pytest.mark.detached


def test_second_lock_in_another_process_is_refused(tmp_path):
    held = project_lock.acquire(tmp_path)
    try:
        script = textwrap.dedent(
            f"""
            import sys
            sys.path.insert(0, {str(__import__("pathlib").Path(project_lock.__file__).parents[2])!r})
            from pytribeam.mcp import project_lock
            try:
                project_lock.acquire({str(tmp_path)!r})
            except project_lock.ProjectLocked as exc:
                print("LOCKED", exc)
            else:
                print("ACQUIRED")
            """
        )
        out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=30)
        assert out.stdout.startswith("LOCKED"), out.stdout + out.stderr
        assert "Another pytribeam MCP server" in out.stdout and "pid" in out.stdout
    finally:
        held.close()


def test_lock_is_released_when_the_owner_exits(tmp_path):
    script = textwrap.dedent(
        f"""
        import sys
        sys.path.insert(0, {str(__import__("pathlib").Path(project_lock.__file__).parents[2])!r})
        from pytribeam.mcp import project_lock
        held = project_lock.acquire({str(tmp_path)!r})
        import os
        os._exit(0)  # exit while holding it, without closing the file
        """
    )
    subprocess.run([sys.executable, "-c", script], check=True, timeout=30)
    project_lock.acquire(tmp_path).close()  # the OS released it: no stale lock


def test_lock_file_names_its_owner(tmp_path):
    held = project_lock.acquire(tmp_path)
    try:
        assert "pid" in (tmp_path / ".lock.owner").read_text()
        # The locked file itself stays empty, so a mandatory (Windows) byte
        # lock never covers anything another process reads or writes.
        assert (tmp_path / ".lock").stat().st_size == 0  # stat, not read: the byte is locked
    finally:
        held.close()


def test_main_refuses_a_locked_project(tmp_path, monkeypatch):
    pytest.importorskip("mcp")
    from pytribeam.mcp import server

    for key in [k for k in __import__("os").environ if k.startswith("PYTRIBEAM_MCP_")]:
        monkeypatch.delenv(key)
    script = textwrap.dedent(
        f"""
        import sys
        sys.path.insert(0, {str(__import__("pathlib").Path(project_lock.__file__).parents[2])!r})
        from pytribeam.mcp import project_lock
        held = project_lock.acquire({str(tmp_path)!r})  # keep it: closing releases
        print("held", flush=True)
        sys.stdin.readline()
        """
    )
    owner = subprocess.Popen([sys.executable, "-c", script], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert owner.stdout.readline().strip() == "held"
        with pytest.raises(SystemExit, match="Another pytribeam MCP server"):
            server.main(["--project-dir", str(tmp_path)])
    finally:
        owner.stdin.close()
        owner.wait(timeout=30)
