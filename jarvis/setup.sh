#!/bin/bash
# One-shot setup for Jarvis on macOS. Safe to re-run.
#
#   ./setup.sh          text + voice loop (no wake word)
#   ./setup.sh --wake   also install the always-on wake word
set -euo pipefail

cd "$(dirname "$0")"

WANT_WAKE=false
[[ "${1:-}" == "--wake" ]] && WANT_WAKE=true

say_step() { printf "\n\033[1m==> %s\033[0m\n" "$1"; }
fail()     { printf "\n\033[31mError:\033[0m %s\n" "$1" >&2; exit 1; }

say_step "Checking Python"
if ! command -v python3 >/dev/null 2>&1; then
    fail "python3 not found. Install it with:
    xcode-select --install
  or, better, with Homebrew (https://brew.sh):
    brew install python@3.12"
fi
PY_OK=$(python3 -c 'import sys; print(1 if sys.version_info >= (3,10) else 0)')
if [[ "$PY_OK" != "1" ]]; then
    CURRENT=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
    fail "Python $CURRENT is too old; Jarvis needs 3.10 or newer. Install a
  current one with Homebrew (https://brew.sh):
    brew install python@3.12
  then run this script again."
fi
echo "Python $(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])') — ok"

say_step "Creating the virtual environment (.venv)"
[[ -d .venv ]] || python3 -m venv .venv

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
