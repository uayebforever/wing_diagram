#!/bin/bash

# Parse arguments from command line into variables, and return (on stdout) the shell commands
# to load these variables.
#
# Usage: arg-parse <arg_names> -- <args_to_process>
#
#    arg_names: argument names, separated by spaces. Flag arguments are bare, while arguments expecting
#               a value end with the equals sign, "="

#               example flag arguments: flag my-flag del
#               example value arguments: name= my-name=
#
#    args_to_process: The actual argument list given to your script, typically "$@".
#
#               NOTE: This should be wrapped in double quotes to ensure that arguments are not accidentally split.
#
#
#    If $USAGE is set in the environment in which this script runs, then its value will be printed after a the error
#    message if there is an argument parsing error.
#
# Output:
#
#     The output will be a valid shell expression that can be `eval`d to load the variables into your script. The
#     variable name will be the same as the <arg_name> given this script (sans an "=" for value arguments).
#     For flag arguments, the value will be "true" unless there is a --no-<flag_name> argument, in which case it will be
#     "false".
#
# Examples:
#
#     Command line:
#       > arg-parse name= flag -- --name=bob --flag
#       name=bob; flag=true
#
#    In a script:
#      parsedArgs=$(arg-parse name= flag -- "$@")
#      eval "${parsedArgs}"
#      # Extracted assignment ensures that an arg-parse error will be surfaced. `eval`ing the arg-parse output
#      # directly will cause any non-zero exit of arg-parse to be suppressed.
#
#    See the arg-parse-hello-world.sh in the tests for a practical example of how to use this script
#
# Notes:
#
#     Arguments are not required: if your script has required arguments, you'll need to check that the corresponding
#         variable has actually been set and respond accordingly. This can easily be done using the shell expansion
#
#             ${arg:?"Error: the argument --arg=<value> is required"}
#
#         (no need for "set -u", although that is also an option.)
#     Repeated arguments are allowed: the variable will be set to the value of the last argument given.
#     Flag arguments can also be repeated, negation of flag arguments is possible with the `--no-<flagname> argument`
#     Only arguments defined can be given, unexpected arguments are an error.
#     Positional arguments are not supported.
#
#


set -e # Exit on error.

function log() {
  if [ -n "$ARG_PARSE_DEBUG" ]; then
    echo "ARG_PARSE_DEBUG: ${1}" 1>&2
  fi
}

function error() {
  message=${1}
  echo "$message" 1>&2
  if [[ -n "$USAGE" ]]; then
    echo "$USAGE" 1>&2
  fi
  exit 90
}

arguments=()
while [[ "$1" != "--" ]]; do
  if [[ "$1" =~ ^[a-zA-Z-][a-zA-Z0-9-]+=[[:graph:]]*$ || "$1" =~ ^[a-zA-Z-][a-zA-Z0-9-]+$ ]]; then
    arguments+=( "$1" )
    shift
  else
    error "arg-parse.sh error: invalid argument definition given: ${1}"
  fi
done

shift  # Remove the "--" separator

if [[ -n "$USAGE" ]]; then
  log "Usage message defined"
fi

while [ $# -gt 0 ]; do
  log "There are $# arguments still to process"
  remaining=$#
  log "Processing argument: ${1}"
  for arg in "${arguments[@]}"; do
    if [[ "$arg" == *"=" ]]; then
      log "Checking against possible argument ${arg}"
      # Argument takes a value
      if [[ "${1}" == "--${arg}"?* ]]; then
        log "Have value for argument ${arg}"
        log "Value is ${1#"--${arg}"}"
        var="${arg%"="}"
        var="${var/-/_}"
        log "Adding assignment ${var}=\${1#"--${arg}"}\";"
        echo -n "${var}=\"${1#"--${arg}"}\"; "
        shift
        break
      elif [[ "${1}" == "--${arg%"="}" ]]; then
        error "Argument error: ${1} requires a value, like \"${1}=foobar\""
      fi
    else
      # Argument does not take a value, so we set it to "true"
      if [[ "${1}" == "--${arg}" ]]; then
        log "Flag argument ${arg} is set."
        var="${arg/-/_}"
        log "Adding assignment ${var}=\"true\"; "
        echo -n "${var}=\"true\"; "
        shift
        break
      elif [[ "${1}" == "--no-${arg}" ]]; then
        log "Flag argument ${arg} is explicitly disabled."
        var="${arg/-/_}"
        log "Adding assignment ${var}=\"false\"; "
        echo -n "${var}=\"false\"; "
        shift
        break
      elif [[ "${1}" == "--${arg}="* ]]; then
        error "Argument error: --${arg} does not accept a value"
      fi
    fi
  done
  if [ $# -eq $remaining ]; then
    # Current argument was not processed.
    error "Unexpected argument: ${1}"
  fi
done
