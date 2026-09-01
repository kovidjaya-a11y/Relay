"""Claude layer: streaming responses, memory tools, prompt caching, and a
degraded-offline fallback via Ollama.

Request shape notes (Claude Opus 5):
- Thinking is adaptive by default; we omit the `thinking` param and control
  spend with output_config.effort (config, default "low" for voice latency).
- Server-side refusal fallbacks are enabled (`fallbacks="default"`), so a
  safety decline is retried on a fallback model within the same call.
- The persona and the memory context are separate cached system blocks:
  the persona never changes; the memory block only changes when memory does.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator

import anthropic
import requests

from .config import Config
from .memory import JOURNAL_KINDS, Memory
from .prompts import PERSONA

FALLBACK_BETA = "server-side-fallback-2026-07-01"

TOOLS = [
    {
        "name": "remember_metric",
        "description": (
            "Record an observation of a fact that changes over time (weight, "
            "cash position, volume, etc.). Append-only: this adds a new data "
            "point, it never overwrites history. Reuse existing metric names "
            "from the current-facts list when one fits."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "metric": {
                    "type": "string",
                    "description": "snake_case metric name, e.g. weight_kg, cash_position_usd",
                },
                "value": {
                    "type": "string",
                    "description": "The value. Numeric strings ('82.5') are stored as numbers for trend queries; anything else is stored as text.",
                },
                "unit": {"type": "string", "description": "Optional unit, e.g. kg, usd, reps"},
                "note": {"type": "string", "description": "Optional context for this data point"},
            },
            "required": ["metric", "value"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "log_journal",
        "description": (
            "Append an entry to the user's running journal of decisions, "
            "updates, notes, and goals."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": list(JOURNAL_KINDS)},
                "content": {"type": "string"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional short tags, e.g. ['health', 'business']",
                },
            },
            "required": ["kind", "content"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "metric_history",
        "description": (
            "Get the recorded history and trend summary for one metric. Use "
            "for questions like 'how has my weight moved since June?'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "metric": {"type": "string"},
                "since_days": {
                    "type": "integer",
                    "description": "Only include observations from the last N days. Omit for all time.",
                },
            },
            "required": ["metric"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "search_journal",
        "description": "Search past journal entries by keyword or tag.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]

_SENTENCE_ENDINGS = (". ", "! ", "? ", ".\n", "!\n", "?\n")

WORKSPACE_HEADER = "anthropic-workspace-id"


def make_client(config: Config) -> anthropic.Anthropic:
    """Build the API client, adding the workspace header when configured.

    Identity-linked API keys are rejected without it; ordinary
    workspace-scoped keys neither need nor mind it.
    """
    workspace_id = config.llm.workspace_id or os.environ.get(
        "ANTHROPIC_WORKSPACE_ID", ""
    )
    if workspace_id:
        return anthropic.Anthropic(
            default_headers={WORKSPACE_HEADER: workspace_id.strip()}
        )
    return anthropic.Anthropic()


def _split_sentences(buffer: str) -> tuple[list[str], str]:
    """Split completed sentences off the front of a streaming text buffer."""
    sentences = []
    while True:
        cut = -1
        for ending in _SENTENCE_ENDINGS:
            idx = buffer.find(ending)
            if idx != -1 and (cut == -1 or idx < cut):
                cut = idx
        if cut == -1:
            return sentences, buffer
        sentences.append(buffer[: cut + 1].strip())
        buffer = buffer[cut + 2 :]


class Assistant:
    """One conversation session. Streams replies sentence-by-sentence so TTS
    can start speaking before the full response is generated."""

    def __init__(self, config: Config, memory: Memory):
        self.config = config
        self.memory = memory
        self.client = make_client(config)
        self.messages: list[dict] = []
        self.last_turn_at: float | None = None
        # System blocks are snapshotted per user turn so a memory write from
        # a tool call can't change the cached prefix mid tool-loop.
        self._turn_system: list[dict] = []

    # -- tool execution ------------------------------------------------------

    def _run_tool(self, name: str, args: dict) -> str:
        if name == "remember_metric":
            row = self.memory.record(
                metric=args["metric"],
                value=args["value"],
                unit=args.get("unit"),
                note=args.get("note"),
            )
            return json.dumps({"recorded": row})
        if name == "log_journal":
            row = self.memory.log(
                kind=args["kind"],
                content=args["content"],
                tags=args.get("tags"),
            )
            return json.dumps({"logged": row})
        if name == "metric_history":
            trend = self.memory.trend(args["metric"], args.get("since_days"))
            history = self.memory.history(
                args["metric"], args.get("since_days"), limit=50
            )
            return json.dumps(
                {
                    "trend": {
                        "count": trend.count,
                        "first": {"value": trend.first_value, "at": trend.first_at},
                        "last": {"value": trend.last_value, "at": trend.last_at},
                        "delta": trend.delta,
                        "min": trend.min_value,
                        "max": trend.max_value,
                        "avg": trend.avg_value,
                    },
                    "observations": history,
                    "known_metrics": self.memory.metrics(),
                }
            )
        if name == "search_journal":
            return json.dumps({"results": self.memory.search_journal(args["query"])})
        return json.dumps({"error": f"unknown tool {name}"})

    # -- main entry point ----------------------------------------------------

    def reset(self) -> None:
        """Start a fresh conversation. Memory persists; the transcript doesn't."""
        self.messages = []

    def _expire_stale_session(self, now: float) -> None:
        """A voice assistant left running for days should not carry this
        morning's conversation into tonight's question."""
        idle_limit = self.config.llm.session_idle_minutes * 60
        if (
            self.last_turn_at is not None
            and idle_limit > 0
            and now - self.last_turn_at > idle_limit
        ):
            self.reset()

    def _trim_history(self) -> None:
        """Keep the last max_turns exchanges.

        Cuts only at real user turns (plain-string content), never between a
        tool_use and its tool_result — splitting that pair is an API error.
        """
        max_turns = self.config.llm.max_turns
        if max_turns <= 0:
            return
        boundaries = [
            i
            for i, m in enumerate(self.messages)
            if m["role"] == "user" and isinstance(m["content"], str)
        ]
        if len(boundaries) <= max_turns:
            return
        self.messages = self.messages[boundaries[-max_turns] :]

    def ask(self, user_text: str) -> Iterator[str]:
        """Send one user turn; yield reply sentences as they stream in."""
        now = time.monotonic()
        self._expire_stale_session(now)
        self.last_turn_at = now

        self.messages.append({"role": "user", "content": user_text})
        self._trim_history()
        self._turn_system = self._system_blocks()
        try:
            yield from self._ask_claude()
        except anthropic.APIConnectionError:
            yield from self._ask_ollama()
        except anthropic.BadRequestError as e:
            raise RuntimeError(self._explain_bad_request(e)) from None

    @staticmethod
    def _explain_bad_request(e: anthropic.BadRequestError) -> str:
        """Turn the API's 400s into something actionable at the terminal."""
        message = str(getattr(e, "message", "") or e)
        if "workspace" in message.lower():
            return (
                "Your API key is identity-linked, so every request must name a "
                "workspace.\nFind the workspace id (starts with 'wrkspc_') at "
                "https://console.anthropic.com/settings/workspaces, then run:\n"
                "    jarvis workspace wrkspc_...\n"
                "Alternatively, create a workspace-scoped API key instead and "
                "store it with `jarvis key`."
            )
        if "credit balance" in message.lower():
            return (
                "Your Anthropic account is out of credit. Top it up at "
                "https://console.anthropic.com/settings/billing"
            )
        return f"The API rejected the request: {message}"

    def _system_blocks(self) -> list[dict]:
        return [
            {
                # Stable prefix: long TTL, since voice use is bursty and the
                # default 5-minute cache would miss between conversations.
                "type": "text",
                "text": PERSONA,
                "cache_control": {"type": "ephemeral", "ttl": "1h"},
            },
            {
                "type": "text",
                "text": self.memory.context_block(),
                "cache_control": {"type": "ephemeral"},
            },
        ]

    def _ask_claude(self) -> Iterator[str]:
        llm = self.config.llm
        while True:
            with self.client.beta.messages.stream(
                model=llm.model,
                max_tokens=llm.max_tokens,
                system=self._turn_system,
                messages=self.messages,
                tools=TOOLS,
                output_config={"effort": llm.effort},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            ) as stream:
                buffer = ""
                for text in stream.text_stream:
                    buffer += text
                    sentences, buffer = _split_sentences(buffer)
                    yield from sentences
                if buffer.strip():
                    yield buffer.strip()
                final = stream.get_final_message()

            self.messages.append(
                {"role": "assistant", "content": final.content}
            )

            if final.stop_reason == "tool_use":
                results = []
                for block in final.content:
                    if block.type == "tool_use":
                        results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": self._run_tool(block.name, dict(block.input)),
                            }
                        )
                self.messages.append({"role": "user", "content": results})
                continue

            if final.stop_reason == "refusal":
                yield "Sorry, I can't help with that one."
            return

    # -- degraded offline mode ------------------------------------------------

    def _ask_ollama(self) -> Iterator[str]:
        """No tools offline: memory is read-only context, answers only."""
        llm = self.config.llm
        if not llm.ollama_model:
            yield "I can't reach the network and no offline model is configured."
            return
        system = "\n\n".join(block["text"] for block in self._turn_system)
        chat_messages = [{"role": "system", "content": system}]
        for m in self.messages:
            if isinstance(m["content"], str):
                chat_messages.append({"role": m["role"], "content": m["content"]})
        try:
            resp = requests.post(
                f"{llm.ollama_url}/api/chat",
                json={
                    "model": llm.ollama_model,
                    "messages": chat_messages,
                    "stream": False,
                },
                timeout=120,
            )
            resp.raise_for_status()
            text = resp.json()["message"]["content"].strip()
        except requests.RequestException:
            yield "I'm offline and the local model isn't responding either."
            return
        self.messages.append({"role": "assistant", "content": text})
        sentences, rest = _split_sentences(text + " ")
        yield from sentences
        if rest.strip():
            yield rest.strip()
