"""Run Jarvis always-on: a macOS launchd user agent wrapping `jarvis listen`.

`jarvis service install` writes ~/Library/LaunchAgents/com.jarvis.assistant.plist
and loads it; the agent starts at login and is restarted if it crashes.
Logs go to ~/.jarvis/logs/.

API keys come from ~/.jarvis/env, which Jarvis reads itself, so the agent
does not depend on launchd inheriting your shell environment. It still runs
through a login shell (`zsh -lc`) so PATH resolves the way it does for you.

Mic permission: run `jarvis listen` once from a terminal first so macOS
shows the microphone prompt; launchd agents can't present it.
"""

from __future__ import annotations

import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

LABEL = "com.jarvis.assistant"


def plist_path() -> Path:
    return Path("~/Library/LaunchAgents").expanduser() / f"{LABEL}.plist"


def log_dir(home: Path) -> Path:
    return home / "logs"


def plist_content(jarvis_bin: str, home: Path) -> bytes:
    logs = log_dir(home)
    return plistlib.dumps(
        {
            "Label": LABEL,
            "ProgramArguments": ["/bin/zsh", "-lc", f"exec {jarvis_bin} listen"],
            "RunAtLoad": True,
            "KeepAlive": {"SuccessfulExit": False},
            "ThrottleInterval": 10,
            "StandardOutPath": str(logs / "jarvis.log"),
            "StandardErrorPath": str(logs / "jarvis.err.log"),
        }
    )


def _launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["launchctl", *args], capture_output=True, text=True
    )


def _gui_domain() -> str:
    import os

    return f"gui/{os.getuid()}"


def install(home: Path) -> None:
    if sys.platform != "darwin":
        raise RuntimeError("jarvis service only supports macOS (launchd)")
    jarvis_bin = shutil.which("jarvis")
    if not jarvis_bin:
        raise RuntimeError(
            "`jarvis` not found on PATH; activate the venv it was installed in "
            "or `pipx install` it so launchd can find a stable path"
        )
    log_dir(home).mkdir(parents=True, exist_ok=True)
    path = plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        _launchctl("bootout", _gui_domain(), str(path))
    path.write_bytes(plist_content(jarvis_bin, home))
    result = _launchctl("bootstrap", _gui_domain(), str(path))
    if result.returncode != 0:
        raise RuntimeError(f"launchctl bootstrap failed: {result.stderr.strip()}")
    print(f"installed and started {LABEL}")
    print(f"logs: {log_dir(home)}/jarvis.log")


def uninstall() -> None:
    path = plist_path()
    if path.exists():
        _launchctl("bootout", _gui_domain(), str(path))
        path.unlink()
        print(f"stopped and removed {LABEL}")
    else:
        print("service is not installed")


def status() -> None:
    result = _launchctl("print", f"{_gui_domain()}/{LABEL}")
    if result.returncode != 0:
        print("not running (install with `jarvis service install`)")
        return
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith(("state", "pid", "last exit", "path")):
            print(line)
