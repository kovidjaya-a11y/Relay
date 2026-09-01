"""`jarvis doctor` — check every part of the setup and say what to fix next.

Written so that one command answers "why isn't this working?", instead of
making someone read a stack trace. Each check returns a status and, when it
fails, the exact command or link that fixes it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .config import PROFILE_TEMPLATE, Config
from .memory import Memory

OK, WARN, FAIL = "ok", "warn", "fail"

MARK = {OK: "\033[32m✓\033[0m", WARN: "\033[33m!\033[0m", FAIL: "\033[31m✗\033[0m"}


@dataclass
class Result:
    status: str
    label: str
    detail: str = ""
    fix: str = ""


def _check_files(cfg: Config) -> list[Result]:
    out = []
    if cfg.home.exists():
        out.append(Result(OK, f"Config folder ({cfg.home})"))
    else:
        out.append(Result(FAIL, "Config folder", "not created", "jarvis init"))
        return out

    if os.environ.get("ANTHROPIC_API_KEY"):
        out.append(Result(OK, "Anthropic API key found"))
    else:
        out.append(
            Result(FAIL, "Anthropic API key", "not set", "jarvis key")
        )

    profile = cfg.profile_path
    # Exact comparison against the template — heuristics misread its own
    # example lines ("- Keep spoken answers short...") as real content.
    if not profile.exists():
        out.append(Result(WARN, "Profile", "missing", "jarvis init"))
    elif profile.read_text().strip() == PROFILE_TEMPLATE.strip():
        out.append(
            Result(
                WARN,
                "Profile is still the blank template",
                "Jarvis won't know anything about you",
                f"open -e {profile}",
            )
        )
    else:
        out.append(Result(OK, "Profile has your details"))
    return out


def _check_memory(cfg: Config) -> Result:
    if not cfg.home.exists():
        # Don't create it as a side effect of diagnosing; `jarvis init` does that.
        return Result(WARN, "Memory database", "not created yet", "jarvis init")
    try:
        memory = Memory(cfg.db_path, cfg.profile_path)
        facts = memory.current_facts()
        memory.close()
        return Result(OK, "Memory database", f"{len(facts)} facts stored")
    except Exception as e:
        return Result(FAIL, "Memory database", str(e))


def _check_audio() -> list[Result]:
    import importlib

    out = []
    for module, label, fix in [
        ("sounddevice", "Microphone support", "brew install portaudio"),
        ("faster_whisper", "Speech to text", 'pip install -e ".[stt]"'),
        ("openwakeword", "Wake word", 'pip install -e ".[wake]"'),
    ]:
        try:
            importlib.import_module(module)
            out.append(Result(OK, label))
        except Exception as e:
            out.append(Result(WARN, label, str(e).split("\n")[0], fix))
    return out


def _check_api(cfg: Config) -> Result:
    """The definitive test: actually call the API."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return Result(FAIL, "API call", "skipped — no key set", "jarvis key")

    import anthropic

    from .llm import make_client

    try:
        client = make_client(cfg)
        client.messages.create(
            model=cfg.llm.model,
            max_tokens=64,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": "Reply with the word: ok"}],
        )
        return Result(OK, "API call succeeded", f"model {cfg.llm.model}")
    except anthropic.BadRequestError as e:
        from .llm import Assistant

        # Guidance goes in `fix` so it surfaces as the next step, not just detail.
        return Result(FAIL, "API call rejected", fix=Assistant._explain_bad_request(e))
    except anthropic.AuthenticationError:
        return Result(
            FAIL, "API key rejected", "the key is not valid", "jarvis key"
        )
    except anthropic.APIConnectionError:
        return Result(WARN, "API unreachable", "no network? offline mode will be used")
    except Exception as e:
        return Result(FAIL, "API call failed", f"{type(e).__name__}: {e}")


def run(cfg: Config) -> int:
    print("Checking your Jarvis setup...\n")

    results = _check_files(cfg)
    results.append(_check_memory(cfg))
    results += _check_audio()
    results.append(_check_api(cfg))

    for r in results:
        line = f"  {MARK[r.status]} {r.label}"
        if r.detail:
            line += f" — {r.detail}"
        print(line)

    problems = [r for r in results if r.status == FAIL and r.fix]
    warnings = [r for r in results if r.status == WARN and r.fix]
    blocking = [r for r in results if r.status == FAIL]

    if problems:
        body = "\n".join(f"    {ln}" for ln in problems[0].fix.splitlines())
        print(f"\n\033[1mDo this next:\033[0m\n{body}")
    elif not blocking:
        print("\n\033[1mEverything works. Start with:\033[0m\n    jarvis chat")
        if warnings:
            print("\nOptional, for voice:")
            for r in warnings:
                print(f"    {r.fix}    ({r.label.lower()})")
    else:
        print("\n\033[1mSomething is wrong above and I don't have a one-line fix.\033[0m")
        print("Paste this output to Claude and it can work out the next step.")

    return 1 if blocking else 0
