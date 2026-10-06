#!/bin/bash

# This script will build the Python package and test on all available matching
# versions of Python.
#
# Usage flags:
#
#    --fast
#        Run only a single Python environment, Python 3.11, and skip E2E tests.
#
#    --e2e
#        Run only E2E tests.

set -o pipefail
set -o nounset
set -o errexit

parsedArgs=$(bin/arg-parse/arg-parse.sh fast -- "$@")
eval "${parsedArgs}"

[ -n "${DEBUG_SH-}" ] && set -o xtrace

SCRIPT_DIR="$(dirname "${BASH_SOURCE[0]}")"

cd "${SCRIPT_DIR}/.."

if [[ ! -f ".venv/bin/activate" ]]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -r requirements_dev.txt

# remove existing builds
rm -f dist/clan_stats-*

#bin/qa_checks.sh
python -m build

if [[ "${fast-}" == "true" ]]; then
  tox -e py311 -m "not e2e"
else
  tox
fi
