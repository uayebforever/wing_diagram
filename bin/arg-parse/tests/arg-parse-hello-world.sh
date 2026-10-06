#!/bin/bash

export USAGE="
Usage: arg-parse-hello-world.sh --name=<name> --greeting=<greeting>

Prints a greeting.

 --name=<name>         Whom to greet.
 --greeting=<greeting> Greeting to use.
"

set -o errexit  # Exit immediately on error.

# This is necessary if you don't know the absolute path to the arg-parse script and it is not on the PATH.
# It is recommended to instead ensure that arg-parse is on the PATH.
scriptDir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default argument values (all arguments are optional here)
bang=false
greeting=Hello
name=World

argumentSource="$("${scriptDir}/../arg-parse.sh" name= greeting= bang -- "$@")"
# NOTE: Separate assignment of arg-parse output necessary to cause errexit on non-zero arg-parse exit code.
eval "${argumentSource}"

echo "Arguments parsed" 1>&2  # Used to confirm exit on arg-parse error in tests.

# NOTE: when using flag values, we should explicitly check for "true"/"false"
if [[ "${bang}" == "true" ]]; then
  suffix="!"
else
  suffix=""
fi

echo "${greeting}, ${name}$suffix"
