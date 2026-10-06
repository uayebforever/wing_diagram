#!/bin/bash

set -o pipefail
set -o nounset
set -o errexit

[ -n "${DEBUG_SH-}" ] && set -o xtrace

for dir in src tests e2e_tests; do
  flake8 $dir
done