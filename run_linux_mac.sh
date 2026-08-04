#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
. .venv/bin/activate
python app.py
