"""Command-line entry points.

Build order (matching the roadmap):
  jarvis init      one-time setup of ~/.jarvis
  jarvis chat      text REPL — proves the LLM + memory loop with no audio
  jarvis ask       one-shot question from the shell
  jarvis talk      voice loop: speak, get spoken answer, repeat (no wake word)
  jarvis listen    phase 2: always-on wake word -> talk loop
  jarvis memory    inspect/edit the store without going through the model
"""

from __future__ import annotations

import argparse
import sys

from .config import CONFIG_TEMPLATE, PROFILE_TEMPLATE, load_config
from .memory import JOURNAL_KINDS, Memory


def _open_memory(cfg):
    return Memory(cfg.db_path, cfg.profile_path)


def cmd_init(cfg, _args) -> None:
    cfg.home.mkdir(parents=True, exist_ok=True)
    config_path = cfg.home / "config.toml"
    if not config_path.exists():
        config_path.write_text(CONFIG_TEMPLATE)
        print(f"wrote {config_path}")
    if not cfg.profile_path.exists():
        cfg.profile_path.write_text(PROFILE_TEMPLATE)
        print(f"wrote {cfg.profile_path} — edit this, it's loaded on every call")
    memory = _open_memory(cfg)
    memory.close()
    print(f"initialized {cfg.db_path}")
    print("\nNext: export ANTHROPIC_API_KEY=... then run `jarvis chat`")


def _reply(assistant, tts, text: str) -> None:
    for sentence in assistant.ask(text):
        print(f"jarvis: {sentence}")
        if tts:
            tts.speak(sentence)


def cmd_chat(cfg, _args) -> None:
    from .llm import Assistant

    memory = _open_memory(cfg)
    assistant = Assistant(cfg, memory)
    print("jarvis text mode — ctrl-d to exit")
    try:
        while True:
            try:
                text = input("you: ").strip()
            except EOFError:
                break
            if not text:
                continue
            _reply(assistant, None, text)
    finally:
        memory.close()


def cmd_ask(cfg, args) -> None:
    from .llm import Assistant

    memory = _open_memory(cfg)
    try:
        assistant = Assistant(cfg, memory)
        for sentence in assistant.ask(" ".join(args.text)):
            print(sentence)
    finally:
        memory.close()


def _one_exchange(cfg, assistant, stt, tts, audio, wake) -> None:
    """Transcribe, answer, then hold the follow-up window open in wake mode."""
    from .audio import record_utterance

    while audio is not None:
        text = stt.transcribe(audio)
        if not text:
            return
        print(f"you: {text}")
        _reply(assistant, tts, text)
        if not wake:
            return
        # Follow-up window: stay in the conversation without the wake word.
        audio = record_utterance(cfg.audio, wait_seconds=cfg.audio.follow_up_window)


def _talk_loop(cfg, assistant, stt, tts, wake=None) -> None:
    from .audio import record_utterance

    while True:
        try:
            if wake:
                print("listening for wake word...")
                wake.wait_for_wake()
                tts.speak("Yes?")
            else:
                print("listening... (speak now, ctrl-c to quit)")
            audio = record_utterance(cfg.audio)
            if audio is None:
                if not wake:
                    print("(heard nothing)")
                continue
            _one_exchange(cfg, assistant, stt, tts, audio, wake)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            # An always-on service must not die on one bad turn: crashing
            # here costs a launchd restart and a slow speech-model reload.
            print(f"error handling turn: {type(e).__name__}: {e}", file=sys.stderr)
            assistant.reset()


def cmd_talk(cfg, _args) -> None:
    from .llm import Assistant
    from .stt import make_stt
    from .tts import make_tts

    memory = _open_memory(cfg)
    try:
        assistant = Assistant(cfg, memory)
        print("loading speech model...")
        stt = make_stt(cfg.stt)
        tts = make_tts(cfg.tts)
        _talk_loop(cfg, assistant, stt, tts)
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        memory.close()


def cmd_listen(cfg, _args) -> None:
    from .llm import Assistant
    from .stt import make_stt
    from .tts import make_tts
    from .wake import make_wake

    memory = _open_memory(cfg)
    wake = None
    try:
        assistant = Assistant(cfg, memory)
        print("loading speech model...")
        stt = make_stt(cfg.stt)
        tts = make_tts(cfg.tts)
        wake = make_wake(cfg.wake)
        _talk_loop(cfg, assistant, stt, tts, wake=wake)
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        if wake:
            wake.close()
        memory.close()


def cmd_service(cfg, args) -> None:
    from . import service

    if args.service_cmd == "install":
        service.install(cfg.home)
    elif args.service_cmd == "uninstall":
        service.uninstall()
    elif args.service_cmd == "status":
        service.status()


def cmd_memory(cfg, args) -> None:
    memory = _open_memory(cfg)
    try:
        if args.memory_cmd == "facts":
            for f in memory.current_facts():
                value = f["value_num"] if f["value_num"] is not None else f["value_text"]
                unit = f" {f['unit']}" if f["unit"] else ""
                print(f"{f['metric']:30} {value}{unit}   (as of {f['observed_at']})")
        elif args.memory_cmd == "record":
            row = memory.record(args.metric, args.value, unit=args.unit, source="cli")
            print(f"recorded {row['metric']} = {row['value_num'] or row['value_text']}")
        elif args.memory_cmd == "history":
            trend = memory.trend(args.metric, args.since_days)
            for obs in reversed(memory.history(args.metric, args.since_days)):
                value = obs["value_num"] if obs["value_num"] is not None else obs["value_text"]
                print(f"{obs['observed_at']}  {value}")
            if trend.delta is not None:
                print(f"-- {trend.count} points, delta {trend.delta:+g} "
                      f"(min {trend.min_value:g}, max {trend.max_value:g})")
        elif args.memory_cmd == "log":
            memory.log(args.kind, " ".join(args.content))
            print("logged")
        elif args.memory_cmd == "journal":
            for e in reversed(memory.recent_journal(args.limit)):
                tags = f" [{e['tags']}]" if e["tags"] else ""
                print(f"{e['ts']} ({e['kind']}){tags}: {e['content']}")
    finally:
        memory.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="jarvis")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="create ~/.jarvis (config, profile, database)")
    sub.add_parser("chat", help="text REPL (no audio)")
    p_ask = sub.add_parser("ask", help="one-shot question")
    p_ask.add_argument("text", nargs="+")
    sub.add_parser("talk", help="voice loop without wake word")
    sub.add_parser("listen", help="always-on wake word voice loop")

    p_svc = sub.add_parser("service", help="run `jarvis listen` as a launchd agent (macOS)")
    svc_sub = p_svc.add_subparsers(dest="service_cmd", required=True)
    svc_sub.add_parser("install", help="install and start the login agent")
    svc_sub.add_parser("uninstall", help="stop and remove the agent")
    svc_sub.add_parser("status", help="show agent state")

    p_mem = sub.add_parser("memory", help="inspect the memory store")
    mem_sub = p_mem.add_subparsers(dest="memory_cmd", required=True)
    mem_sub.add_parser("facts", help="latest value of every metric")
    p_rec = mem_sub.add_parser("record", help="record a metric observation")
    p_rec.add_argument("metric")
    p_rec.add_argument("value")
    p_rec.add_argument("--unit")
    p_hist = mem_sub.add_parser("history", help="history + trend for a metric")
    p_hist.add_argument("metric")
    p_hist.add_argument("--since-days", type=int)
    p_log = mem_sub.add_parser("log", help="add a journal entry")
    p_log.add_argument("kind", choices=JOURNAL_KINDS)
    p_log.add_argument("content", nargs="+")
    p_journal = mem_sub.add_parser("journal", help="recent journal entries")
    p_journal.add_argument("--limit", type=int, default=20)

    args = parser.parse_args()
    cfg = load_config()

    handlers = {
        "init": cmd_init,
        "chat": cmd_chat,
        "ask": cmd_ask,
        "talk": cmd_talk,
        "listen": cmd_listen,
        "service": cmd_service,
        "memory": cmd_memory,
    }
    try:
        handlers[args.cmd](cfg, args)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
