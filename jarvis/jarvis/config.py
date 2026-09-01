"""Configuration: ~/.jarvis/config.toml with sane defaults.

Everything lives under one data dir (default ~/.jarvis, override with
JARVIS_HOME) so the whole assistant state is one folder you can read,
edit, and back up: config.toml, profile.md, jarvis.db.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("JARVIS_HOME", "~/.jarvis")).expanduser()


def load_env_file() -> None:
    """Load ~/.jarvis/env (KEY=value lines) into the environment.

    Keeps API keys in one file you can edit, instead of scattered across
    shell profiles — and means the launchd agent sees them too. Real
    environment variables always win, so you can still override per-run.
    """
    path = data_dir() / "env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass
class LLMConfig:
    model: str = "claude-opus-5"
    max_tokens: int = 16000
    # Required only for identity-linked API keys, which must name the
    # workspace each request acts in. Falls back to ANTHROPIC_WORKSPACE_ID.
    workspace_id: str = ""
    # Voice replies should be snappy; raise to "high" if you start asking
    # Jarvis for real analysis rather than quick answers.
    effort: str = "low"
    # Ollama model used when the Anthropic API is unreachable (degraded
    # offline mode). Empty string disables the fallback.
    ollama_model: str = "llama3.1:8b"
    ollama_url: str = "http://localhost:11434"
    # Always-on hygiene: start a fresh conversation after this much silence,
    # and never carry more than this many exchanges within one conversation.
    # Long-term recall comes from the memory store, not the transcript.
    session_idle_minutes: float = 10.0
    max_turns: int = 20


@dataclass
class STTConfig:
    # "faster-whisper" (portable) or "mlx" (fastest on Apple Silicon).
    backend: str = "faster-whisper"
    model: str = "small.en"
    mlx_model: str = "mlx-community/whisper-small.en-mlx"


@dataclass
class TTSConfig:
    # "say" (macOS built-in, zero setup), "kokoro" (local, natural),
    # "elevenlabs" (hosted, most natural, needs ELEVENLABS_API_KEY).
    backend: str = "say"
    say_voice: str = "Samantha"
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"
    elevenlabs_model: str = "eleven_flash_v2_5"
    kokoro_voice: str = "af_heart"


@dataclass
class WakeConfig:
    # "openwakeword" (default, free/open) or "porcupine" (requires a paid
    # Picovoice plan since their free tier ended June 2026).
    backend: str = "openwakeword"
    # openWakeWord: a built-in model name ("hey_jarvis", "alexa", ...) or a
    # path to a custom-trained .onnx model.
    model: str = "hey_jarvis"
    threshold: float = 0.5
    # Porcupine only: custom .ppn path + PICOVOICE_ACCESS_KEY in the env.
    keyword_path: str = ""
    sensitivity: float = 0.6


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    # Seconds of trailing silence that ends an utterance.
    silence_after: float = 0.9
    max_utterance: float = 30.0
    # After Jarvis answers in wake-word mode, keep listening this many
    # seconds for a follow-up before requiring the wake word again.
    follow_up_window: float = 6.0


@dataclass
class Config:
    llm: LLMConfig = field(default_factory=LLMConfig)
    stt: STTConfig = field(default_factory=STTConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    wake: WakeConfig = field(default_factory=WakeConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)

    @property
    def home(self) -> Path:
        return data_dir()

    @property
    def db_path(self) -> Path:
        return self.home / "jarvis.db"

    @property
    def profile_path(self) -> Path:
        return self.home / "profile.md"


def load_config() -> Config:
    load_env_file()
    cfg = Config()
    path = data_dir() / "config.toml"
    if not path.exists():
        return cfg
    raw = tomllib.loads(path.read_text())
    for section_name, section in (
        ("llm", cfg.llm),
        ("stt", cfg.stt),
        ("tts", cfg.tts),
        ("wake", cfg.wake),
        ("audio", cfg.audio),
    ):
        for key, value in raw.get(section_name, {}).items():
            if hasattr(section, key):
                setattr(section, key, value)
    return cfg


CONFIG_TEMPLATE = """\
# Jarvis configuration. Every key is optional; these are the defaults.

[llm]
model = "claude-opus-5"
effort = "low"            # low | medium | high | xhigh | max
ollama_model = "llama3.1:8b"  # offline fallback; "" disables

[stt]
backend = "faster-whisper"  # or "mlx" on Apple Silicon
model = "small.en"

[tts]
backend = "say"           # say | kokoro | elevenlabs

[wake]
backend = "openwakeword"  # or "porcupine" (paid Picovoice plan)
model = "hey_jarvis"      # built-in model name, or path to a custom .onnx
threshold = 0.5           # raise if you get false wakes, lower if it misses
"""

def set_env_var(name: str, value: str) -> Path:
    """Upsert one KEY=value line in ~/.jarvis/env, leaving the rest alone."""
    path = data_dir() / "env"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text().splitlines() if path.exists() else []

    replaced = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        if stripped.partition("=")[0].strip() == name:
            lines[i] = f"{name}={value}"
            replaced = True
            break
    if not replaced:
        lines.append(f"{name}={value}")

    path.write_text("\n".join(lines) + "\n")
    path.chmod(0o600)  # it holds API keys
    return path


ENV_TEMPLATE = """\
# API keys for Jarvis. This file is read on every run.
# Keep it private — it is created with owner-only permissions.

ANTHROPIC_API_KEY=

# Optional: only needed if you set [tts] backend = "elevenlabs"
# ELEVENLABS_API_KEY=
"""

PROFILE_TEMPLATE = """\
# Profile

<!-- Jarvis loads this file into every conversation. Edit it freely; -->
<!-- plain markdown, no special format. Keep it short and current. -->

## About me
- Name:
- Location / timezone:
- Work:

## Goals
-

## Standing preferences
- Keep spoken answers short unless I ask for detail.
"""
