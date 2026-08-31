import pytest

from jarvis.memory import Memory


@pytest.fixture
def memory(tmp_path):
    profile = tmp_path / "profile.md"
    profile.write_text("# Profile\n- Name: Kovid\n")
    m = Memory(tmp_path / "test.db", profile)
    yield m
    m.close()


def test_record_numeric_and_text_values(memory):
    row = memory.record("weight_kg", "82.5", unit="kg")
    assert row["value_num"] == 82.5
    assert row["value_text"] is None

    row = memory.record("volume", "settled")
    assert row["value_num"] is None
    assert row["value_text"] == "settled"


def test_metric_names_are_normalized(memory):
    memory.record("Cash Position", 1000)
    assert memory.metrics() == ["cash_position"]


def test_current_facts_returns_latest_per_metric(memory):
    memory.record("weight_kg", 84, observed_at="2026-06-01T08:00:00Z")
    memory.record("weight_kg", 82.5, observed_at="2026-08-01T08:00:00Z")
    memory.record("cash_position_usd", 5000, observed_at="2026-07-01T08:00:00Z")

    facts = {f["metric"]: f for f in memory.current_facts()}
    assert facts["weight_kg"]["value_num"] == 82.5
    assert facts["cash_position_usd"]["value_num"] == 5000


def test_current_facts_tie_break_prefers_newest_insert(memory):
    memory.record("weight_kg", 84, observed_at="2026-08-01T08:00:00Z")
    memory.record("weight_kg", 83, observed_at="2026-08-01T08:00:00Z")
    facts = memory.current_facts()
    assert len(facts) == 1
    assert facts[0]["value_num"] == 83


def test_trend_delta_min_max(memory):
    memory.record("weight_kg", 84, observed_at="2026-06-01T08:00:00Z")
    memory.record("weight_kg", 83, observed_at="2026-07-01T08:00:00Z")
    memory.record("weight_kg", 82.5, observed_at="2026-08-01T08:00:00Z")

    t = memory.trend("weight_kg")
    assert t.count == 3
    assert t.first_value == 84
    assert t.last_value == 82.5
    assert t.delta == -1.5
    assert t.min_value == 82.5
    assert t.max_value == 84


def test_trend_ignores_text_values_for_stats(memory):
    memory.record("volume", 120, observed_at="2026-06-01T08:00:00Z")
    memory.record("volume", "settled", observed_at="2026-07-01T08:00:00Z")
    t = memory.trend("volume")
    assert t.count == 2
    assert t.last_value == 120  # latest *numeric* point


def test_history_since_days_filters(memory):
    memory.record("weight_kg", 90, observed_at="2020-01-01T00:00:00Z")
    memory.record("weight_kg", 82.5)  # now
    assert len(memory.history("weight_kg")) == 2
    assert len(memory.history("weight_kg", since_days=30)) == 1


def test_journal_log_and_search(memory):
    memory.log("decision", "Dropped the agency retainer to focus on product", tags=["business"])
    memory.log("note", "Sleep has been rough this week")

    assert len(memory.recent_journal()) == 2
    results = memory.search_journal("retainer")
    assert len(results) == 1
    assert results[0]["kind"] == "decision"
    assert memory.search_journal("business")  # tags are searchable


def test_journal_rejects_unknown_kind(memory):
    with pytest.raises(ValueError):
        memory.log("rant", "nope")


def test_context_block_contains_profile_facts_journal(memory):
    memory.record("weight_kg", 82.5, unit="kg")
    memory.log("decision", "Ship jarvis phase one")

    block = memory.context_block()
    assert "Kovid" in block
    assert "weight_kg: 82.5 kg" in block
    assert "Ship jarvis phase one" in block


def test_context_block_empty_store(tmp_path):
    m = Memory(tmp_path / "empty.db")
    try:
        block = m.context_block()
        assert "(none recorded yet)" in block
        assert "(empty)" in block
    finally:
        m.close()


def test_persistence_across_reopen(tmp_path):
    m = Memory(tmp_path / "persist.db")
    m.record("cash_position_usd", 5000)
    m.close()

    m2 = Memory(tmp_path / "persist.db")
    try:
        assert m2.current_facts()[0]["value_num"] == 5000
    finally:
        m2.close()
