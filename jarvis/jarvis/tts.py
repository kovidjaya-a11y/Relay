"""Text-to-speech backends, called one sentence at a time as the LLM streams.

- say:        macOS built-in. Zero setup, lowest latency, robotic-ish. Default
              so the loop works on day one.
- kokoro:     Kokoro-82M via kokoro-onnx. Local, natural, realtime on
              M-series. The offline natural-voice option.
- elevenlabs: Flash v2.5 over HTTPS. Most natural, ~75 ms model latency
              (plus network). Needs ELEVENLABS_API_KEY.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

import requests

from .config import TTSConfig


class TTS:
    def speak(self, text: str) -> None:
        raise NotImplementedError


class SayTTS(TTS):
    def __init__(self, cfg: TTSConfig):
        self.voice = cfg.say_voice

    def speak(self, text: str) -> None:
        subprocess.run(["say", "-v", self.voice, text], check=False)


class KokoroTTS(TTS):
    def __init__(self, cfg: TTSConfig):
        import sounddevice as sd
        from kokoro_onnx import Kokoro

        self._sd = sd
        self.voice = cfg.kokoro_voice
        # Model + voice files: https://github.com/thewh1teagle/kokoro-onnx/releases
        model_dir = os.path.expanduser("~/.jarvis/models")
        self.kokoro = Kokoro(
            os.path.join(model_dir, "kokoro-v1.0.onnx"),
            os.path.join(model_dir, "voices-v1.0.bin"),
        )

    def speak(self, text: str) -> None:
        samples, sample_rate = self.kokoro.create(text, voice=self.voice, speed=1.1)
        self._sd.play(samples, sample_rate)
        self._sd.wait()


class ElevenLabsTTS(TTS):
    def __init__(self, cfg: TTSConfig):
        self.api_key = os.environ.get("ELEVENLABS_API_KEY", "")
        if not self.api_key:
            raise RuntimeError(
                "ELEVENLABS_API_KEY is not set — add it to ~/.jarvis/env"
            )
        self.voice_id = cfg.elevenlabs_voice_id
        self.model = cfg.elevenlabs_model
        self.player = shutil.which("afplay") or shutil.which("ffplay") or shutil.which("mpv")
        if not self.player:
            raise RuntimeError("no audio player found (afplay/ffplay/mpv)")

    def speak(self, text: str) -> None:
        resp = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}",
            headers={"xi-api-key": self.api_key},
            json={
                "text": text,
                "model_id": self.model,
                "output_format": "mp3_44100_64",
            },
            timeout=30,
        )
        resp.raise_for_status()
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(resp.content)
            path = f.name
        try:
            cmd = [self.player, path]
            if "ffplay" in self.player:
                cmd = [self.player, "-nodisp", "-autoexit", "-loglevel", "quiet", path]
            elif "mpv" in self.player:
                cmd = [self.player, "--really-quiet", path]
            subprocess.run(cmd, check=False)
        finally:
            os.unlink(path)


def make_tts(cfg: TTSConfig) -> TTS:
    if cfg.backend == "say":
        return SayTTS(cfg)
    if cfg.backend == "kokoro":
        return KokoroTTS(cfg)
    if cfg.backend == "elevenlabs":
        return ElevenLabsTTS(cfg)
    raise ValueError(f"unknown tts backend {cfg.backend!r}")
