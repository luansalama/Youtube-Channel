#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
python -m unittest discover -s "$ROOT/tests" -v
python -m mcstudio --root "$ROOT" validate
