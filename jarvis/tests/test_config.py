"""~/.jarvis/env keeps API keys in one editable file rather than scattered
across shell profiles — and is what the launchd agent reads too."""

import os

import pytest

from jarvis.config import load_config, load_env_file


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
