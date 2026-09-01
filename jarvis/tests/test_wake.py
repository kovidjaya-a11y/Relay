"""Wake word backend selection, and the openWakeWord contract we rely on.

The openWakeWord tests skip unless the [wake] extra is installed, so the
suite still runs on a bare `pip install -e ".[dev]"`.
"""

import pytest

from jarvis.config import WakeConfig
from jarvis.wake import make_wake


def test_unknown_backend_is_rejected():
    with pytest.raises(ValueError, match="unknown wake backend"):
        make_wake(WakeConfig(backend="whisper-ears"))


def test_porcupine_requires_an_access_key(monkeypatch):
    pytest.importorskip("pvporcupine")
    monkeypatch.delenv("PICOVOICE_ACCESS_KEY", raising=False)
    with pytest.raises(RuntimeError, match="PICOVOICE_ACCESS_KEY"):
        make_wake(WakeConfig(backend="porcupine"))


def test_default_model_is_a_real_pretrained_name():
    """`hey_jarvis` must exist upstream — it's the whole zero-setup story."""
    openwakeword = pytest.importorskip("openwakeword")
    assert WakeConfig().model in openwakeword.MODELS


@pytest.mark.parametrize("bad_name", ["hey jarvis", "jarvis", "Hey_Jarvis"])
def test_near_miss_model_names_are_rejected(bad_name):
    """openWakeWord accepts "hey jarvis" and silently loads a different
    model — a wake word that never fires. We must reject it ourselves."""
    pytest.importorskip("openwakeword")
    with pytest.raises(RuntimeError, match="hey_jarvis"):
        make_wake(WakeConfig(model=bad_name))


def test_bad_custom_model_path_is_reported_clearly():
    pytest.importorskip("openwakeword")
    with pytest.raises(RuntimeError, match="Could not load wake word model"):
        make_wake(WakeConfig(model="/nonexistent/my_phrase.onnx"))


def test_predict_returns_scores_we_can_threshold():
    """Pins the upstream API wait_for_wake() depends on."""
    pytest.importorskip("openwakeword")
    import numpy as np

    from jarvis.wake import OWW_FRAME_SAMPLES, OpenWakeWordListener

    listener = make_wake(WakeConfig())
    assert isinstance(listener, OpenWakeWordListener)

    silence = np.zeros(OWW_FRAME_SAMPLES, dtype=np.int16)
    scores = listener.model.predict(silence)

    assert isinstance(scores, dict) and scores
    assert all(isinstance(v, float) for v in scores.values())
    assert max(scores.values()) < listener.threshold  # silence must not wake it
    listener.model.reset()  # used to clear buffers after a detection
