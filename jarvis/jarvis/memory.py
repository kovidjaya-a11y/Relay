"""Local memory store: SQLite for time-series facts + journal, markdown profile.

Design goals:
- Owned by the user: plain SQLite at ~/.jarvis/jarvis.db (open it with any
  sqlite client) and a hand-editable ~/.jarvis/profile.md.
- Facts that change over time (weight, cash position, volume, ...) are
  append-only *observations*, never overwritten — so trends stay queryable.
  "Current state" is just the latest observation per metric (the
  `current_facts` view).
- A journal keeps a running log of decisions, updates and notes.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

JOURNAL_KINDS = ("decision", "update", "note", "goal")

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    id          INTEGER PRIMARY KEY,
    metric      TEXT NOT NULL,
    value_num   REAL,
    value_text  TEXT,
    unit        TEXT,
    observed_at TEXT NOT NULL,
    source      TEXT NOT NULL DEFAULT 'voice',
    note        TEXT,
    CHECK (value_num IS NOT NULL OR value_text IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_obs_metric_time
    ON observations(metric, observed_at);

CREATE TABLE IF NOT EXISTS journal (
    id      INTEGER PRIMARY KEY,
    ts      TEXT NOT NULL,
    kind    TEXT NOT NULL CHECK (kind IN ('decision','update','note','goal')),
    content TEXT NOT NULL,
    tags    TEXT
);
CREATE INDEX IF NOT EXISTS idx_journal_ts ON journal(ts);

CREATE VIEW IF NOT EXISTS current_facts AS
SELECT metric, value_num, value_text, unit, observed_at, note
FROM (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY metric ORDER BY observed_at DESC, id DESC
    ) AS rn
    FROM observations
)
WHERE rn = 1;
"""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_metric(metric: str) -> str:
    return metric.strip().lower().replace(" ", "_")


@dataclass
class Trend:
    metric: str
    count: int
    first_value: float | None
    first_at: str | None
    last_value: float | None
    last_at: str | None
    min_value: float | None
    max_value: float | None
    avg_value: float | None

    @property
    def delta(self) -> float | None:
        if self.first_value is None or self.last_value is None:
            return None
        return self.last_value - self.first_value


class Memory:
    def __init__(self, db_path: Path | str, profile_path: Path | str | None = None):
        self.db_path = Path(db_path)
        self.profile_path = Path(profile_path) if profile_path else None
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # -- observations ------------------------------------------------------

    def record(
        self,
        metric: str,
        value: str | float | int,
        unit: str | None = None,
        note: str | None = None,
        observed_at: str | None = None,
        source: str = "voice",
    ) -> dict:
        metric = _normalize_metric(metric)
        value_num: float | None = None
        value_text: str | None = None
        if isinstance(value, (int, float)):
            value_num = float(value)
        else:
            try:
                value_num = float(str(value).replace(",", "").strip())
            except ValueError:
                value_text = str(value).strip()
        cur = self.conn.execute(
            "INSERT INTO observations (metric, value_num, value_text, unit, observed_at, source, note)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (metric, value_num, value_text, unit, observed_at or _now(), source, note),
        )
        self.conn.commit()
        return self.get_observation(cur.lastrowid)

    def get_observation(self, obs_id: int) -> dict:
        row = self.conn.execute(
            "SELECT * FROM observations WHERE id = ?", (obs_id,)
        ).fetchone()
        return dict(row) if row else {}

    def current_facts(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM current_facts ORDER BY metric"
        ).fetchall()
        return [dict(r) for r in rows]

    def history(
        self, metric: str, since_days: int | None = None, limit: int = 100
    ) -> list[dict]:
        metric = _normalize_metric(metric)
        query = "SELECT * FROM observations WHERE metric = ?"
        params: list = [metric]
        if since_days is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
            query += " AND observed_at >= ?"
            params.append(cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"))
        query += " ORDER BY observed_at DESC, id DESC LIMIT ?"
        params.append(limit)
        return [dict(r) for r in self.conn.execute(query, params).fetchall()]

    def trend(self, metric: str, since_days: int | None = None) -> Trend:
        rows = self.history(metric, since_days=since_days, limit=10000)
        rows = list(reversed(rows))  # chronological
        numeric = [r for r in rows if r["value_num"] is not None]
        values = [r["value_num"] for r in numeric]
        return Trend(
            metric=_normalize_metric(metric),
            count=len(rows),
            first_value=numeric[0]["value_num"] if numeric else None,
            first_at=numeric[0]["observed_at"] if numeric else None,
            last_value=numeric[-1]["value_num"] if numeric else None,
            last_at=numeric[-1]["observed_at"] if numeric else None,
            min_value=min(values) if values else None,
            max_value=max(values) if values else None,
            avg_value=sum(values) / len(values) if values else None,
        )

    def metrics(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT metric FROM observations ORDER BY metric"
        ).fetchall()
        return [r["metric"] for r in rows]

    # -- journal -----------------------------------------------------------

    def log(self, kind: str, content: str, tags: list[str] | None = None) -> dict:
        if kind not in JOURNAL_KINDS:
            raise ValueError(f"kind must be one of {JOURNAL_KINDS}, got {kind!r}")
        cur = self.conn.execute(
            "INSERT INTO journal (ts, kind, content, tags) VALUES (?, ?, ?, ?)",
            (_now(), kind, content.strip(), ",".join(tags) if tags else None),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM journal WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return dict(row)

    def recent_journal(self, limit: int = 10) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM journal ORDER BY ts DESC, id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def search_journal(self, query: str, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM journal WHERE content LIKE ? OR tags LIKE ?"
            " ORDER BY ts DESC, id DESC LIMIT ?",
            (f"%{query}%", f"%{query}%", limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- context for the LLM ------------------------------------------------

    def profile_text(self) -> str:
        if self.profile_path and self.profile_path.exists():
            return self.profile_path.read_text().strip()
        return "(no profile file yet — run `jarvis init`)"

    def context_block(self, journal_limit: int = 10) -> str:
        """Markdown block injected into the system prompt on every call."""
        lines = ["# User profile", self.profile_text(), "", "# Current facts"]
        facts = self.current_facts()
        if facts:
            for f in facts:
                value = f["value_num"] if f["value_num"] is not None else f["value_text"]
                unit = f" {f['unit']}" if f["unit"] else ""
                note = f" — {f['note']}" if f["note"] else ""
                lines.append(f"- {f['metric']}: {value}{unit} (as of {f['observed_at']}){note}")
        else:
            lines.append("(none recorded yet)")
        lines += ["", f"# Recent journal (last {journal_limit})"]
        entries = self.recent_journal(journal_limit)
        if entries:
            for e in reversed(entries):
                tags = f" [{e['tags']}]" if e["tags"] else ""
                lines.append(f"- {e['ts']} ({e['kind']}){tags}: {e['content']}")
        else:
            lines.append("(empty)")
        return "\n".join(lines)
