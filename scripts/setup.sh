#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m mcstudio --root "$ROOT" init
python -m unittest discover -s tests -v
python -m mcstudio --root "$ROOT" validate
