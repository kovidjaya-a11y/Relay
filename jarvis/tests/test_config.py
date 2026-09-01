"""~/.jarvis/env keeps API keys in one editable file rather than scattered
across shell profiles — and is what the launchd agent reads too."""

import os

import pytest

from jarvis.config import load_config, load_env_file, set_env_var


@pytest.fixture
def jarvis_home(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_HOME", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return tmp_path


def test_env_file_populates_the_environment(jarvis_home):
    (jarvis_home / "env").write_text("ANTHROPIC_API_KEY=sk-ant-from-file\n")
    load_env_file()
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-from-file"


def test_real_environment_wins_over_the_file(jarvis_home, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-shell")
    (jarvis_home / "env").write_text("ANTHROPIC_API_KEY=sk-ant-from-file\n")
    load_env_file()
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-from-shell"


def test_comments_blanks_and_quotes_are_handled(jarvis_home):
    (jarvis_home / "env").write_text(
        "\n# a comment\n\n"
        'ELEVENLABS_API_KEY="quoted-value"\n'
        "  PICOVOICE_ACCESS_KEY = spaced-value  \n"
        "not_a_pair\n"
    )
    load_env_file()
    assert os.environ["ELEVENLABS_API_KEY"] == "quoted-value"
    assert os.environ["PICOVOICE_ACCESS_KEY"] == "spaced-value"


def test_missing_env_file_is_not_an_error(jarvis_home):
    load_env_file()  # no file written
    assert "ANTHROPIC_API_KEY" not in os.environ


def test_load_config_reads_the_env_file(jarvis_home):
    (jarvis_home / "env").write_text("ANTHROPIC_API_KEY=sk-ant-via-load-config\n")
    load_config()
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-via-load-config"


def test_set_env_var_replaces_in_place_and_keeps_the_rest(jarvis_home):
    (jarvis_home / "env").write_text(
        "# a comment\n"
        "ANTHROPIC_API_KEY=old-key\n"
        "ELEVENLABS_API_KEY=keep-me\n"
    )
    set_env_var("ANTHROPIC_API_KEY", "new-key")

    text = (jarvis_home / "env").read_text()
    assert "ANTHROPIC_API_KEY=new-key" in text
    assert "old-key" not in text
    assert "ELEVENLABS_API_KEY=keep-me" in text
    assert "# a comment" in text


def test_set_env_var_appends_when_absent(jarvis_home):
    (jarvis_home / "env").write_text("ELEVENLABS_API_KEY=abc\n")
    set_env_var("ANTHROPIC_API_KEY", "brand-new")
    text = (jarvis_home / "env").read_text()
    assert "ELEVENLABS_API_KEY=abc" in text
    assert "ANTHROPIC_API_KEY=brand-new" in text


def test_set_env_var_ignores_commented_out_lines(jarvis_home):
    """A commented example must not be mistaken for the real setting."""
    (jarvis_home / "env").write_text("# ANTHROPIC_API_KEY=example\n")
    set_env_var("ANTHROPIC_API_KEY", "real-key")
    lines = (jarvis_home / "env").read_text().splitlines()
    assert "# ANTHROPIC_API_KEY=example" in lines
    assert "ANTHROPIC_API_KEY=real-key" in lines


def test_set_env_var_creates_the_file_private(jarvis_home):
    path = set_env_var("ANTHROPIC_API_KEY", "k")
    assert path.exists()
    assert oct(path.stat().st_mode)[-3:] == "600"


def test_a_stored_key_round_trips_into_the_environment(jarvis_home):
    set_env_var("ANTHROPIC_API_KEY", "sk-ant-round-trip")
    load_env_file()
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-round-trip"


def test_config_toml_overrides_defaults(jarvis_home):
    (jarvis_home / "config.toml").write_text(
        '[llm]\nmodel = "claude-sonnet-5"\nmax_turns = 4\n'
        '[tts]\nbackend = "elevenlabs"\n'
    )
    cfg = load_config()
    assert cfg.llm.model == "claude-sonnet-5"
    assert cfg.llm.max_turns == 4
    assert cfg.tts.backend == "elevenlabs"
    assert cfg.stt.backend == "faster-whisper"  # untouched default
