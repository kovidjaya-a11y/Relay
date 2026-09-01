"""Client construction: identity-linked API keys must name a workspace on
every request, or the API rejects them with a 400."""

import httpx
import pytest

from jarvis.config import Config
from jarvis.llm import WORKSPACE_HEADER, Assistant, make_client
from jarvis.memory import Memory


@pytest.fixture(autouse=True)
def _api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("ANTHROPIC_WORKSPACE_ID", raising=False)


def _sent_headers(client) -> httpx.Headers:
    """Headers the SDK would actually put on the wire for a Messages call."""
    from anthropic._models import FinalRequestOptions

    options = FinalRequestOptions.construct(
        method="post", url="/v1/messages", json_data={}
    )
    return client._build_request(options).headers


def test_no_workspace_header_by_default():
    client = make_client(Config())
    assert WORKSPACE_HEADER not in _sent_headers(client)


def test_workspace_id_from_config_is_sent():
    cfg = Config()
    cfg.llm.workspace_id = "wrkspc_from_config"
    assert _sent_headers(make_client(cfg))[WORKSPACE_HEADER] == "wrkspc_from_config"


def test_workspace_id_from_environment_is_sent(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "wrkspc_from_env")
    assert _sent_headers(make_client(Config()))[WORKSPACE_HEADER] == "wrkspc_from_env"


def test_config_wins_over_environment(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "wrkspc_from_env")
    cfg = Config()
    cfg.llm.workspace_id = "wrkspc_from_config"
    assert _sent_headers(make_client(cfg))[WORKSPACE_HEADER] == "wrkspc_from_config"


def test_surrounding_whitespace_is_stripped():
    cfg = Config()
    cfg.llm.workspace_id = "  wrkspc_padded\n"
    assert _sent_headers(make_client(cfg))[WORKSPACE_HEADER] == "wrkspc_padded"


@pytest.mark.parametrize(
    "api_message, expected",
    [
        (
            "anthropic-workspace-id is required when authenticating with an "
            "identity-linked API key; send the id of the workspace this "
            "request acts in.",
            "jarvis workspace",
        ),
        ("Your credit balance is too low to access the API.", "billing"),
        ("some other problem", "some other problem"),
    ],
)
def test_bad_request_messages_are_actionable(api_message, expected, tmp_path):
    memory = Memory(tmp_path / "c.db")
    try:
        assistant = Assistant(Config(), memory)
        error = type("E", (), {"message": api_message})()
        assert expected in assistant._explain_bad_request(error)
    finally:
        memory.close()
