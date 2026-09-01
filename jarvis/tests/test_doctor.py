"""`jarvis doctor` must name the single next action for each failure mode."""

import anthropic
import httpx
import pytest

from jarvis import doctor
from jarvis.config import PROFILE_TEMPLATE, Config, load_config


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_HOME", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_WORKSPACE_ID", raising=False)
    return tmp_path


def _bad_request(message: str) -> anthropic.BadRequestError:
    return anthropic.BadRequestError(
        "Error code: 400",
        response=httpx.Response(400, request=httpx.Request("POST", "https://x")),
        body={"type": "error", "error": {"message": message}},
    )


def _run(capsys, cfg) -> tuple[int, str]:
    code = doctor.run(cfg)
    return code, capsys.readouterr().out


def test_missing_config_folder_says_run_init(home, monkeypatch, capsys):
    missing = home / "not-created-yet"  # tmp_path itself always exists
    monkeypatch.setenv("JARVIS_HOME", str(missing))
    code, out = _run(capsys, load_config())
    assert code == 1
    assert "jarvis init" in out
    # Diagnosing must not create the folder as a side effect.
    assert not missing.exists()


def test_missing_key_says_run_jarvis_key(home, capsys):
    (home / "profile.md").write_text("- Name: Kovid\n")
    code, out = _run(capsys, load_config())
    assert code == 1
    assert "jarvis key" in out


def test_untouched_profile_is_only_a_warning(home, monkeypatch, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    (home / "profile.md").write_text(PROFILE_TEMPLATE)
    monkeypatch.setattr(doctor, "_check_api", lambda cfg: doctor.Result(doctor.OK, "API"))
    code, out = _run(capsys, load_config())
    assert code == 0  # a blank profile must not block starting
    assert "blank template" in out


def test_filled_profile_passes(home, monkeypatch, capsys):
    (home / "profile.md").write_text(PROFILE_TEMPLATE + "\n- Name: Kovid\n")
    monkeypatch.setattr(doctor, "_check_api", lambda cfg: doctor.Result(doctor.OK, "API"))
    _, out = _run(capsys, load_config())
    assert "Profile has your details" in out


def test_workspace_error_names_the_workspace_command(home, monkeypatch, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    monkeypatch.setattr(
        doctor, "make_client", None, raising=False
    )

    class FakeClient:
        class messages:
            @staticmethod
            def create(**kwargs):
                raise _bad_request(
                    "anthropic-workspace-id is required when authenticating "
                    "with an identity-linked API key."
                )

    import jarvis.llm as llm

    monkeypatch.setattr(llm, "make_client", lambda cfg: FakeClient())
    code, out = _run(capsys, load_config())
    assert code == 1
    assert "jarvis workspace" in out
    assert "Do this next" in out


def test_out_of_credit_points_at_billing(home, monkeypatch, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")

    class FakeClient:
        class messages:
            @staticmethod
            def create(**kwargs):
                raise _bad_request("Your credit balance is too low.")

    import jarvis.llm as llm

    monkeypatch.setattr(llm, "make_client", lambda cfg: FakeClient())
    code, out = _run(capsys, load_config())
    assert code == 1
    assert "billing" in out


def test_all_clear_tells_you_to_start(home, monkeypatch, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    (home / "profile.md").write_text("- Name: Kovid\n")
    monkeypatch.setattr(
        doctor, "_check_api", lambda cfg: doctor.Result(doctor.OK, "API call succeeded")
    )
    monkeypatch.setattr(doctor, "_check_audio", lambda: [doctor.Result(doctor.OK, "Audio")])
    code, out = _run(capsys, load_config())
    assert code == 0
    assert "jarvis chat" in out


def test_offline_is_a_warning_not_a_failure(home, monkeypatch, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    (home / "profile.md").write_text("- Name: Kovid\n")

    class FakeClient:
        class messages:
            @staticmethod
            def create(**kwargs):
                raise anthropic.APIConnectionError(
                    request=httpx.Request("POST", "https://x")
                )

    import jarvis.llm as llm

    monkeypatch.setattr(llm, "make_client", lambda cfg: FakeClient())
    code, out = _run(capsys, load_config())
    assert code == 0  # offline mode exists, so this isn't fatal
    assert "unreachable" in out.lower()
