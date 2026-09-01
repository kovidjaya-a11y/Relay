"""Phase 2: always-on wake word.

Default backend is openWakeWord (Apache-2.0, fully local, no account):
- The pretrained "hey_jarvis" model ships with the library — zero setup.
- For a different phrase, train a custom model with their notebook
  (https://github.com/dscripka/openWakeWord#training-new-models) and point
  [wake] model at the resulting .onnx file.

Porcupine remains available as [wake] backend = "porcupine" for anyone with
a paid Picovoice plan — their free tier was discontinued June 30, 2026, and
new signups are approval-gated, so it is no longer the default.
"""

from __future__ import annotations

import os

from .config import WakeConfig

# openWakeWord models expect 16 kHz int16 audio in 80 ms frames.
OWW_SAMPLE_RATE = 16000
OWW_FRAME_SAMPLES = 1280


class WakeWordListener:
    def wait_for_wake(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        pass


class OpenWakeWordListener(WakeWordListener):
    def __init__(self, cfg: WakeConfig):
        import numpy as np
        import openwakeword
        from openwakeword.model import Model

        self._np = np
        self.threshold = cfg.threshold
        # First run downloads the shared feature models (and the pretrained
        # wake models) to the openwakeword cache; no-op afterwards.
        openwakeword.utils.download_models()

        # cfg.model is either a built-in name ("hey_jarvis") or a path to a
        # custom-trained .onnx. Validate names ourselves: openWakeWord accepts
        # a near-miss like "hey jarvis" and silently loads a *different* model
        # rather than erroring, which would leave a wake word that never fires.
        is_path = os.path.sep in cfg.model or cfg.model.endswith(".onnx")
        if not is_path and cfg.model not in openwakeword.MODELS:
            available = ", ".join(sorted(openwakeword.MODELS))
            raise RuntimeError(
                f"Unknown wake word model {cfg.model!r}. Set [wake] model in "
                f"~/.jarvis/config.toml to one of: {available} — or to the "
                f"path of a custom-trained .onnx file."
            )
        try:
            self.model = Model(
                wakeword_models=[cfg.model], inference_framework="onnx"
            )
        except Exception as e:
            raise RuntimeError(
                f"Could not load wake word model {cfg.model!r}: {e}"
            ) from e

    def wait_for_wake(self) -> None:
        import sounddevice as sd

        with sd.RawInputStream(
            samplerate=OWW_SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=OWW_FRAME_SAMPLES,
        ) as stream:
            while True:
                data, _overflowed = stream.read(OWW_FRAME_SAMPLES)
                frame = self._np.frombuffer(bytes(data), dtype=self._np.int16)
                scores = self.model.predict(frame)
                if max(scores.values()) >= self.threshold:
                    # Clear internal buffers so residual audio can't re-trigger.
                    self.model.reset()
                    return


class PorcupineListener(WakeWordListener):
    def __init__(self, cfg: WakeConfig):
        import pvporcupine
        from pvrecorder import PvRecorder

        access_key = os.environ.get("PICOVOICE_ACCESS_KEY", "")
        if not access_key:
            raise RuntimeError("PICOVOICE_ACCESS_KEY is not set")
        if not cfg.keyword_path or not os.path.exists(cfg.keyword_path):
            raise RuntimeError(
                "No Porcupine keyword model; set [wake] keyword_path to your "
                ".ppn file (requires a paid Picovoice plan)"
            )
        self.porcupine = pvporcupine.create(
            access_key=access_key,
            keyword_paths=[cfg.keyword_path],
            sensitivities=[cfg.sensitivity],
        )
        self.recorder = PvRecorder(frame_length=self.porcupine.frame_length)

    def wait_for_wake(self) -> None:
        self.recorder.start()
        try:
            while True:
                frame = self.recorder.read()
                if self.porcupine.process(frame) >= 0:
                    return
        finally:
            # Release the mic so record_utterance() can open its own stream.
            self.recorder.stop()

    def close(self) -> None:
        self.recorder.delete()
        self.porcupine.delete()


def make_wake(cfg: WakeConfig) -> WakeWordListener:
    if cfg.backend == "openwakeword":
        return OpenWakeWordListener(cfg)
    if cfg.backend == "porcupine":
        return PorcupineListener(cfg)
    raise ValueError(f"unknown wake backend {cfg.backend!r}")
