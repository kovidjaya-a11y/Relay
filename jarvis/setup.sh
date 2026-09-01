#!/bin/bash
# One-shot setup for Jarvis on macOS. Safe to re-run.
#
#   ./setup.sh          text + voice loop (no wake word)
#   ./setup.sh --wake   also install the always-on wake word
set -euo pipefail

cd "$(dirname "$0")"

WANT_WAKE=false
WAKE_FLAG=""
if [[ "${1:-}" == "--wake" ]]; then
    WANT_WAKE=true
    WAKE_FLAG=" --wake"
fi

say_step() { printf "\n\033[1m==> %s\033[0m\n" "$1"; }
fail()     { printf "\n\033[31mError:\033[0m %s\n" "$1" >&2; exit 1; }

say_step "Checking Python"
# macOS ships Python 3.9, and Homebrew's newer Python often does not take
# over the plain `python3` name, so search explicitly rather than trusting it.
find_python() {
    local c
    for c in python3.14 python3.13 python3.12 python3.11 python3.10 \
             /opt/homebrew/bin/python3.14 /opt/homebrew/bin/python3.13 \
             /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11 \
             /opt/homebrew/bin/python3.10 /opt/homebrew/bin/python3 \
             /usr/local/bin/python3.12 /usr/local/bin/python3.11 \
             /usr/local/bin/python3.10 /usr/local/bin/python3 python3; do
        if command -v "$c" >/dev/null 2>&1 \
           && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' \
              >/dev/null 2>&1; then
            command -v "$c"
            return 0
        fi
    done
    return 1
}

if ! PYTHON=$(find_python); then
    CURRENT="none found"
    command -v python3 >/dev/null 2>&1 && \
        CURRENT="you have $(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
    fail "Jarvis needs Python 3.10 or newer ($CURRENT).

  1. If you don't have Homebrew yet, install it (asks for your password,
     takes a few minutes):

       /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"

     then run the two 'Next steps' lines it prints at the end.

  2. Install Python:

       brew install python@3.12

  3. Run this script again:

       ./setup.sh$WAKE_FLAG"
fi
echo "Using $PYTHON ($("$PYTHON" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])'))"

say_step "Creating the virtual environment (.venv)"
# Rebuild the venv if it was made with a Python that is now gone or too old.
if [[ -d .venv ]] && ! ./.venv/bin/python -c \
     'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' >/dev/null 2>&1; then
    echo "existing .venv uses an unusable Python — recreating it"
    rm -rf .venv
fi
[[ -d .venv ]] || "$PYTHON" -m venv .venv

say_step "Installing Jarvis and its dependencies (a few minutes the first time)"
EXTRAS="audio,stt,dev"
$WANT_WAKE && EXTRAS="$EXTRAS,wake"
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet -e ".[$EXTRAS]"

say_step "Checking that the audio and speech pieces load"
CHECK_OUT=$(./.venv/bin/python - <<'PY'
import importlib

# (module, what it does, how to fix it)
checks = [
    ("sounddevice", "microphone access", "brew install portaudio"),
    ("numpy", "audio maths", ""),
    ("faster_whisper", "speech to text", ""),
]
try:
    import openwakeword  # noqa: F401
    checks.append(("openwakeword", "wake word", ""))
except ImportError:
    pass

for name, purpose, fix in checks:
    try:
        importlib.import_module(name)
    except Exception as e:
        print(f"FAIL\t{name}\t{purpose}\t{fix}\t{e}")
print("DONE")
PY
) || true

if ! grep -q '^DONE$' <<<"$CHECK_OUT"; then
    fail "The install did not complete. Output:
$CHECK_OUT"
fi
VOICE_BROKEN=false
if grep -q '^FAIL' <<<"$CHECK_OUT"; then
    VOICE_BROKEN=true
    # Not fatal: `jarvis chat` needs no microphone, so let setup finish and
    # flag this as something to fix before `jarvis talk`.
    printf "\n\033[33mHeads up — the voice pieces aren't ready yet:\033[0m\n"
    while IFS=$'\t' read -r _ name purpose fix err; do
        [[ "$name" ]] || continue
        printf "  • %s (%s): %s\n" "$name" "$purpose" "$err"
        [[ "$fix" ]] && printf "    Fix with: %s   then re-run ./setup.sh%s\n" "$fix" "$WAKE_FLAG"
    done < <(grep '^FAIL' <<<"$CHECK_OUT")
    printf "\nTyping to Jarvis ('jarvis chat') works regardless — carrying on.\n"
else
    echo "all good"
fi

say_step "Setting up ~/.jarvis"
./.venv/bin/jarvis init

cat <<EOF

$(printf "\033[1m==> Done. Two things to fill in:\033[0m")

  1. Your Anthropic API key — get one at
     https://console.anthropic.com/settings/keys
     then paste it into this file after "ANTHROPIC_API_KEY=":

       open -e ~/.jarvis/env

  2. A few lines about yourself, so Jarvis knows who it's talking to:

       open -e ~/.jarvis/profile.md

$(printf "\033[1m==> Then start it:\033[0m")

     cd $(pwd)
     source .venv/bin/activate
     jarvis chat     # type at it first, no microphone needed
EOF
if $VOICE_BROKEN; then
    cat <<EOF

  (Voice is not usable until you fix the item flagged above and re-run
   ./setup.sh$WAKE_FLAG — typing works now either way.)
EOF
else
    echo "     jarvis talk     # then talk to it"
    if $WANT_WAKE; then
        echo '     jarvis listen   # then just say "hey jarvis"'
    fi
fi
echo
