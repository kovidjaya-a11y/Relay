"""Microphone capture: record one utterance, stop on trailing silence.

Uses webrtcvad when installed (robust), falls back to an RMS energy gate.
Returns 16 kHz mono float32 numpy audio, which both STT backends accept.
"""

from __future__ import annotations

import numpy as np

from .config import AudioConfig

FRAME_MS = 30


def _make_vad():
    try:
        import webrtcvad

        vad = webrtcvad.Vad(2)

        def is_speech(frame_bytes: bytes, sample_rate: int) -> bool:
            return vad.is_speech(frame_bytes, sample_rate)

        return is_speech
    except ImportError:
        def is_speech(frame_bytes: bytes, sample_rate: int) -> bool:
            frame = np.frombuffer(frame_bytes, dtype=np.int16)
            rms = np.sqrt(np.mean(frame.astype(np.float64) ** 2))
            return rms > 300

        return is_speech


def record_utterance(cfg: AudioConfig, wait_seconds: float = 10.0) -> np.ndarray | None:
    """Block until the user speaks, return audio once they stop.

    Returns None if nothing was said within wait_seconds.
    """
    import sounddevice as sd

    sample_rate = cfg.sample_rate
    frame_len = int(sample_rate * FRAME_MS / 1000)
    is_speech = _make_vad()

    silence_frames_needed = int(cfg.silence_after * 1000 / FRAME_MS)
    max_frames = int(cfg.max_utterance * 1000 / FRAME_MS)
    wait_frames = int(wait_seconds * 1000 / FRAME_MS)

    frames: list[bytes] = []
    started = False
    silent_run = 0
    waited = 0

    with sd.RawInputStream(
        samplerate=sample_rate, channels=1, dtype="int16", blocksize=frame_len
    ) as stream:
        while True:
            data, _overflowed = stream.read(frame_len)
            frame_bytes = bytes(data)
            speech = is_speech(frame_bytes, sample_rate)

            if not started:
                waited += 1
                if speech:
                    started = True
                    frames.append(frame_bytes)
                elif waited > wait_frames:
                    return None
                continue

            frames.append(frame_bytes)
            silent_run = 0 if speech else silent_run + 1
            if silent_run >= silence_frames_needed or len(frames) >= max_frames:
                break

    pcm = np.frombuffer(b"".join(frames), dtype=np.int16)
    return pcm.astype(np.float32) / 32768.0
