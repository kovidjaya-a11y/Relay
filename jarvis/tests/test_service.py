import plistlib
from pathlib import Path

from jarvis.service import LABEL, plist_content


def test_plist_is_valid_and_complete(tmp_path):
    data = plistlib.loads(plist_content("/usr/local/bin/jarvis", tmp_path))

    assert data["Label"] == LABEL
    assert data["ProgramArguments"][:2] == ["/bin/zsh", "-lc"]
    assert "exec /usr/local/bin/jarvis listen" in data["ProgramArguments"][2]
    assert data["RunAtLoad"] is True
    # Restart on crash, but not on clean exit (e.g. after `service uninstall`).
    assert data["KeepAlive"] == {"SuccessfulExit": False}
    assert data["StandardOutPath"] == str(tmp_path / "logs" / "jarvis.log")
    assert data["StandardErrorPath"] == str(tmp_path / "logs" / "jarvis.err.log")


def test_plist_quotes_home_path(tmp_path):
    home = Path(tmp_path) / "custom home"
    data = plistlib.loads(plist_content("/opt/jarvis/bin/jarvis", home))
    assert str(home / "logs" / "jarvis.log") == data["StandardOutPath"]
