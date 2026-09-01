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
     jarvis talk     # then talk to it
EOF
$WANT_WAKE && cat <<'EOF'
     jarvis listen   # then just say "hey jarvis"
EOF
echo
