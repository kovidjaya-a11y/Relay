# Jarvis — personal voice assistant

Always-listening local wake word → local speech-to-text → Claude (with your
persistent memory in context) → low-latency speech. Laptop CLI first, then
phone and car.

Target machine: macOS on Apple Silicon. Budget: $20–100/mo API spend.
Offline: degraded mode (local LLM fallback, local TTS, everything else is
already local).

```
 mic ──► wake word ──► record until silence ──► STT ──► Claude + tools ──► TTS ──► speaker
         (Porcupine,     (webrtcvad)             (whisper,   │    ▲          (sentence-
          always on,                              local)     ▼    │           streamed)
          ~1% CPU)                                        ~/.jarvis/
                                                    profile.md + jarvis.db
```

## Component decisions

### 1. Wake word — **openWakeWord** (Porcupine only if you'll pay for it)

> Picovoice discontinued its free tier: free AccessKeys stopped working
> June 30, 2026, new signups are an approval-gated trial for product teams,
> and the paid Foundation plan is priced for startups (reported ~$6k/yr).
> That removes Porcupine as an option for a personal project and flips the
> original recommendation.

| | openWakeWord | Porcupine |
|---|---|---|
| Cost / access | Apache-2.0, no account, fully local | Paid plan, approval-gated signup |
| Custom wake word | Pretrained **"hey_jarvis"** ships with the library; other phrases via their training notebook (synthetic TTS data, a few hours of tinkering) | Instant training in their console |
| Accuracy / false wakes | Good; tune `[wake] threshold` (raise for fewer false wakes) | Best in class |
| CPU | Low (ONNX, small models) | ~1% of one core |
| Phone later | No iOS SDK — phase 3 will need its own approach (see roadmap) | First-party iOS/Android SDKs |

**Recommendation: openWakeWord** with the stock `hey_jarvis` model — it is
literally the wake word this project wants, pretrained, free, and zero-setup.
Both backends are implemented in `wake.py`; `[wake] backend = "porcupine"`
still works if you ever have a paid key.

### 2. Speech-to-text — **local Whisper** (small.en), pluggable

Latency is dominated by three things: model size, hardware path, and network.
On an M-series Mac a local small model beats hosted APIs on total latency for
short utterances (no upload round-trip) and it's a hard requirement for
degraded-offline anyway.

| Option | Typical latency for a 3–5 s utterance | Notes |
|---|---|---|
| **mlx-whisper `small.en` (Metal)** | ~0.3–0.6 s | Fastest on Apple Silicon. `[stt] backend = "mlx"` |
| faster-whisper `small.en` int8 (CPU) | ~0.7–1.5 s | Portable default (also runs on the car/phone-adjacent hardware later) |
| Hosted (Groq whisper-large-v3-turbo, Deepgram) | ~0.3–1 s + network | Better accuracy on hard audio, but network-dependent and another key to manage |

**Recommendation:** start with `faster-whisper small.en` (default), switch to
`mlx` backend on your Mac for the extra speed. Accuracy of `small.en` is fine
for command/dictation-style speech; bump to `distil-large-v3` if you find
mis-transcriptions, at ~2x the latency.

### 3. LLM — Anthropic API (Claude Opus 5)

- Model: `claude-opus-5` (config: `[llm] model`), adaptive thinking, effort
  `low` by default for voice snappiness — raise it when you want real analysis.
- **Streaming, sentence by sentence**: TTS starts speaking the first sentence
  while the rest is still generating. This is the single biggest perceived-
  latency win in the whole pipeline.
- **Prompt caching**: the persona and your memory context are cached system
  blocks, so repeat calls bill a fraction of the input tokens.
- **Server-side refusal fallbacks are enabled** (`fallbacks="default"`): if a
  request is declined by safety filters, the API retries it on a fallback
  model within the same call. Remove `betas`/`fallbacks` in `llm.py` if you
  don't want this.
- **Memory tools**: the model can `remember_metric`, `log_journal`,
  `metric_history`, `search_journal` — so "I weighed 82.5 this morning"
  gets recorded without you doing anything.
- **Session hygiene** (matters once it runs for days): the conversation
  resets after `[llm] session_idle_minutes` of silence (default 10) and is
  capped at `[llm] max_turns` exchanges (default 20), trimmed only at whole
  user turns so tool pairs are never split. Long-term recall is the memory
  store's job, not the transcript's — so cost and context stay flat no
  matter how long the service has been up.
- **Offline fallback**: if the API is unreachable, the same conversation is
  answered by Ollama (`llama3.1:8b` by default) with your memory as read-only
  context. Install [Ollama](https://ollama.com) and `ollama pull llama3.1:8b`.

Cost estimate: a heavy day of 100 voice exchanges ≈ 200–400K input tokens
(mostly cache reads) + ~30K output ≈ $1.50–3/day at Opus 5 rates — inside
your budget. Set `model = "claude-sonnet-5"` to cut that ~60% if usage grows.

### 4. Text-to-speech — pluggable, three tiers

| Backend | Latency to first audio | Voice quality | Offline |
|---|---|---|---|
| `say` (macOS built-in) | ~instant | Robotic-but-fine (Siri voices help: `say -v '?'`) | Yes |
| `kokoro` (Kokoro-82M local) | ~0.3–0.8 s/sentence on M-series | Natural, best local option | Yes |
| `elevenlabs` (Flash v2.5) | ~75 ms model + network | Most natural by far | No |

**Recommendation:** prove the loop with `say` (zero setup), then set
`backend = "elevenlabs"` for daily use (pennies per day at Flash rates within
your budget) with `kokoro` as the offline voice. All three speak one sentence
at a time as Claude streams.

### 5. Memory — SQLite + markdown, owned by you

Everything lives in `~/.jarvis/` (override with `JARVIS_HOME`):

- **`profile.md`** — who you are, goals, standing preferences. Plain
  markdown, edit it in any editor; loaded into every call.
- **`jarvis.db`** — SQLite, open it with any client (`sqlite3 ~/.jarvis/jarvis.db`).

Facts that change over time are **append-only observations** — recording a
new weight never overwrites the old one, so trends stay queryable:

```sql
CREATE TABLE observations (
    id          INTEGER PRIMARY KEY,
    metric      TEXT NOT NULL,     -- 'weight_kg', 'cash_position_usd', ...
    value_num   REAL,              -- numeric values → trend math
    value_text  TEXT,              -- or a state like 'settled'
    unit        TEXT,
    observed_at TEXT NOT NULL,     -- ISO-8601 UTC; backdating allowed
    source      TEXT NOT NULL,     -- 'voice' | 'cli' | ...
    note        TEXT
);

CREATE TABLE journal (             -- running log of decisions & updates
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    kind TEXT CHECK (kind IN ('decision','update','note','goal')),
    content TEXT NOT NULL,
    tags TEXT
);

-- "Current state" is just the latest observation per metric:
CREATE VIEW current_facts AS
SELECT metric, value_num, value_text, unit, observed_at, note FROM (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY metric ORDER BY observed_at DESC, id DESC) AS rn
    FROM observations
) WHERE rn = 1;
```

Query trends directly, no assistant needed:

```sql
-- weight over the last 90 days
SELECT observed_at, value_num FROM observations
WHERE metric = 'weight_kg' AND observed_at >= datetime('now', '-90 days')
ORDER BY observed_at;
```

or via the CLI: `jarvis memory history weight_kg --since-days 90`.

## Setup

```bash
cd jarvis
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[audio,stt,dev]"     # add: stt-mlx, tts-local, wake as you go

export ANTHROPIC_API_KEY=sk-ant-...
jarvis init                            # creates ~/.jarvis, edit profile.md
jarvis chat                            # phase 1a: prove the loop, text only
jarvis talk                            # phase 1b: full voice loop
```

Try in `chat`: *"I weighed 82.5 kg this morning"* → then
`jarvis memory facts` in another shell to see it landed.

## Phase 2: always-on wake word

1. `pip install -e ".[wake]"` — installs openWakeWord. No account, no key;
   the pretrained models (including `hey_jarvis`, the default) download to
   a local cache on first run.
2. Test in the foreground: `jarvis listen`, say "hey jarvis". Run it from a
   terminal at least once so macOS shows the mic permission prompt. Tune
   `[wake] threshold` in `~/.jarvis/config.toml` if it false-wakes (raise)
   or misses you (lower).
3. Want a different phrase? Train a custom model with the
   [openWakeWord training notebook](https://github.com/dscripka/openWakeWord#training-new-models)
   and set `[wake] model = "/path/to/your_phrase.onnx"`.
4. Make it survive reboots: `jarvis service install` — a launchd login agent
   that starts Jarvis at login and restarts it if it crashes. Logs land in
   `~/.jarvis/logs/`. Manage with `jarvis service status` / `uninstall`.

After each answer Jarvis keeps listening for a follow-up for a few seconds
(`[audio] follow_up_window`, default 6), so you can continue the conversation
without repeating the wake word.

## Roadmap

- [x] **Phase 1a** — text CLI: Claude + memory tools + persistent store
- [x] **Phase 1b** — voice loop: VAD mic capture → whisper → Claude → TTS (code ready; test on the Mac)
- [x] **Phase 2** — wake word + always-on: `jarvis listen` (openWakeWord `hey_jarvis`), follow-up window, `jarvis service install` launchd agent (code ready; needs a real mic to verify)
- [ ] **Phase 3a** — phone: thin iOS app (AVFoundation mic → your Mac or a small server running this package behind an API). openWakeWord has no iOS SDK, so start push-to-talk / Action-button; evaluate on-device wake (Core ML port, or Porcupine if paying) later
- [ ] **Phase 3b** — car: CarPlay is locked down; practical path is the phone app + Bluetooth audio, wake word running on the phone
- [ ] **Barge-in** — interrupt Jarvis mid-sentence instead of waiting out a wrong answer (needs interruptible TTS playback)
- [ ] Later: memory summarization job (compress old journal into profile.md), calendar/home integrations as more tools
