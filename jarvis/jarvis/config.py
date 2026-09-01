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


@dataclass
class LLMConfig:
    model: str = "claude-opus-5"
    max_tokens: int = 16000
    # Voice replies should be snappy; raise to "high" if you start asking
    # Jarvis for real analysis rather than quick answers.
    effort: str = "low"
    # Ollama model used when the Anthropic API is unreachable (degraded
    # offline mode). Empty string disables the fallback.
    ollama_model: str = "llama3.1:8b"
    ollama_url: str = "http://localhost:11434"


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
