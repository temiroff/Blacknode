"""Stopping the helper processes nodes spawn, on every platform.

Runtimes start streams and workers detached so they survive a cook, which also
means nothing else will clean them up. Each runtime grew its own terminate
helper built on ``os.killpg`` - POSIX-only, so on Windows it raises, falls back
to killing just the direct child, and leaves the rest of the tree holding the
camera or the port.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys

_IS_WINDOWS = sys.platform == "win32"


def terminate_tree(proc: subprocess.Popen | None, *, timeout: float = 3.0) -> bool:
    """Stop a spawned process and everything it started. True if it was alive."""
    if proc is None or proc.poll() is not None:
        return False

    if _IS_WINDOWS:
        # taskkill /T walks the child tree; Popen.terminate would stop only the
        # launcher and orphan the interpreter actually holding the device.
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                timeout=timeout + 2,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            try:
                proc.kill()
            except Exception:
                return False
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            return False
        except Exception:
            try:
                proc.terminate()
            except Exception:
                return False

    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        if not _IS_WINDOWS:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                pass
        try:
            proc.kill()
        except Exception:
            pass
    return True
