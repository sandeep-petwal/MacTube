#!/bin/bash

cd -- "$(dirname -- "$0")" || exit 1

# Finder may launch with a minimal PATH.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

if [[ -x .venv/bin/python ]]; then
    python=.venv/bin/python
elif command -v python3.13 >/dev/null 2>&1; then
    python=python3.13
else
    printf '%s\n' 'Python 3.13 is required. See README.md for installation instructions.' >&2
    exit 1
fi

exec "$python" mactube.py "$@"
