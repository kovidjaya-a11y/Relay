"""Speech-to-text backends. All local, per the latency + offline requirement.

- faster-whisper: portable (CTranslate2, int8 on CPU). Default.
- mlx-whisper: fastest on Apple Silicon (Metal). Set [stt] backend = "mlx".

Both take 16 kHz mono float32 numpy audio and return text. Imports are lazy
so the package works without the optional extras installed.
"""

from __future__ import annotations

from .config import STTConfig


class STT:
    def transcribe(self, audio) -> str:  # audio: np.ndarray float32 @ 16kHz
        raise NotImplementedError


class FasterWhisperSTT(STT):
    def __init__(self, cfg: STTConfig):
        from faster_whisper import WhisperModel

        self.model = WhisperModel(cfg.model, device="cpu", compute_type="int8")

    def transcribe(self, audio) -> str:
        segments, _info = self.model.transcribe(
            audio, language="en", beam_size=1, vad_filter=True
        )
        return " ".join(s.text.strip() for s in segments).strip()


class MLXWhisperSTT(STT):
    def __init__(self, cfg: STTConfig):
        import mlx_whisper

        self._mlx_whisper = mlx_whisper
        self.model_repo = cfg.mlx_model

    def transcribe(self, audio) -> str:
        result = self._mlx_whisper.transcribe(
            audio, path_or_hf_repo=self.model_repo, language="en"
        )
        return result["text"].strip()


def make_stt(cfg: STTConfig) -> STT:
    if cfg.backend == "mlx":
        return MLXWhisperSTT(cfg)
    if cfg.backend == "faster-whisper":
        return FasterWhisperSTT(cfg)
    raise ValueError(f"unknown stt backend {cfg.backend!r}")
