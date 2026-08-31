"""Phase 2: always-on wake word via Picovoice Porcupine.

Setup (one-time, ~5 minutes):
1. Create a free account at https://console.picovoice.ai
2. Copy your AccessKey and export it:  export PICOVOICE_ACCESS_KEY=...
3. Train your custom wake phrase (type it, click train — it's instant),
   download the macOS .ppn file, and point [wake] keyword_path at it.

Porcupine runs fully offline at ~1% CPU; only the console training step
needs the network.
"""

from __future__ import annotations

import os

from .config import WakeConfig


class WakeWordListener:
    def __init__(self, cfg: WakeConfig):
        import pvporcupine
        from pvrecorder import PvRecorder

        access_key = os.environ.get("PICOVOICE_ACCESS_KEY", "")
        if not access_key:
            raise RuntimeError("PICOVOICE_ACCESS_KEY is not set")
        if not cfg.keyword_path or not os.path.exists(cfg.keyword_path):
            raise RuntimeError(
                "No wake word model. Train one at https://console.picovoice.ai "
                "and set [wake] keyword_path in ~/.jarvis/config.toml"
            )
        self.porcupine = pvporcupine.create(
            access_key=access_key,
            keyword_paths=[cfg.keyword_path],
            sensitivities=[cfg.sensitivity],
        )
        self.recorder = PvRecorder(frame_length=self.porcupine.frame_length)

    def wait_for_wake(self) -> None:
        """Block until the wake word is heard."""
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
