#!/bin/bash

# Directory containing this script.
scriptDir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"


# Install Bats if necessary
if ! which bats; then
  git clone https://github.com/bats-core/bats-core.git
  pushd bats-core
    ./install.sh /usr/local
  popd
fi

bats "${scriptDir}"/*.bats
