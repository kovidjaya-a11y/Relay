"""Session hygiene for the always-on service: stale conversations expire,
long ones get trimmed without corrupting tool pairing, and the cached system
prefix is stable within a turn.

These exercise the pure conversation-state helpers — no network calls.
"""

import pytest

from jarvis.config import Config
from jarvis.llm import Assistant
from jarvis.memory import Memory


@pytest.fixture
def assistant(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-not-used")
    memory = Memory(tmp_path / "s.db")
    a = Assistant(Config(), memory)
    yield a
    memory.close()


def test_idle_conversation_is_dropped(assistant):
    assistant.config.llm.session_idle_minutes = 10
    assistant.messages = [{"role": "user", "content": "this morning's chat"}]
    assistant.last_turn_at = 1000.0

    assistant._expire_stale_session(1000.0 + 11 * 60)
    assert assistant.messages == []


def test_recent_conversation_is_kept(assistant):
    assistant.config.llm.session_idle_minutes = 10
    assistant.messages = [{"role": "user", "content": "still talking"}]
    assistant.last_turn_at = 1000.0

    assistant._expire_stale_session(1000.0 + 60)
    assert len(assistant.messages) == 1


def test_first_turn_never_resets(assistant):
    assistant.messages = [{"role": "user", "content": "hello"}]
    assistant.last_turn_at = None

    assistant._expire_stale_session(99999.0)
    assert len(assistant.messages) == 1


def test_zero_idle_minutes_disables_expiry(assistant):
    assistant.config.llm.session_idle_minutes = 0
    assistant.messages = [{"role": "user", "content": "keep me"}]
    assistant.last_turn_at = 1.0

    assistant._expire_stale_session(1_000_000.0)
    assert len(assistant.messages) == 1


def test_trim_keeps_last_n_exchanges(assistant):
    assistant.config.llm.max_turns = 2
    for i in range(5):
        assistant.messages.append({"role": "user", "content": f"q{i}"})
        assistant.messages.append({"role": "assistant", "content": f"a{i}"})

    assistant._trim_history()
    assert assistant.messages[0] == {"role": "user", "content": "q3"}
    assert len(assistant.messages) == 4


def test_trim_is_noop_below_limit(assistant):
    assistant.config.llm.max_turns = 20
    assistant.messages = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "a"},
    ]
    assistant._trim_history()
    assert len(assistant.messages) == 2


def test_trim_never_splits_a_tool_pair(assistant):
    """Cutting between a tool_use and its tool_result is a 400 from the API."""
    assistant.config.llm.max_turns = 1
    assistant.messages = [
        {"role": "user", "content": "old question"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t1"}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1"}]},
        {"role": "assistant", "content": "old answer"},
        {"role": "user", "content": "new question"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t2"}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t2"}]},
    ]

    assistant._trim_history()

    # Kept exactly the newest exchange, starting at a real user turn.
    assert assistant.messages[0] == {"role": "user", "content": "new question"}
    # Every remaining tool_result still has its tool_use ahead of it.
    tool_uses = {
        block["id"]
        for m in assistant.messages
        if isinstance(m["content"], list)
        for block in m["content"]
        if block.get("type") == "tool_use"
    }
    tool_results = {
        block["tool_use_id"]
        for m in assistant.messages
        if isinstance(m["content"], list)
        for block in m["content"]
        if block.get("type") == "tool_result"
    }
    assert tool_results <= tool_uses


def test_reset_clears_transcript_not_memory(assistant):
    assistant.memory.record("weight_kg", 82.5)
    assistant.messages = [{"role": "user", "content": "hi"}]

    assistant.reset()

    assert assistant.messages == []
    assert assistant.memory.current_facts()[0]["value_num"] == 82.5


def test_persona_block_is_cached_with_long_ttl(assistant):
    persona, context = assistant._system_blocks()
    # Voice use is bursty; the 5-minute default would miss between chats.
    assert persona["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert context["cache_control"] == {"type": "ephemeral"}


def test_turn_system_snapshot_survives_a_memory_write(assistant):
    """A tool writing to memory mid-loop must not shift the cached prefix."""
    assistant._turn_system = assistant._system_blocks()
    before = assistant._turn_system[1]["text"]

    assistant.memory.record("cash_position_usd", 5000)

    assert assistant._turn_system[1]["text"] == before
    # ...and the next turn does pick the new fact up.
    assert "cash_position_usd" in assistant._system_blocks()[1]["text"]
