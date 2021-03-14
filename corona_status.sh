#!/usr/bin/env bash
# exit on error, exit on undefined variables, error on failing pipe commands
set -euo pipefail
# error on commands in command substitutions
shopt -s inherit_errexit # bash >= 4.4

echo2() {
  echo "$@" >&2
}

log() {
  echo2 "[$(date '+%F %H:%M:%S')] ${1}"
}

debug() {
  if [[ ${LOGLEVEL} == "DEBUG" || ${LOGLVL} -ge 4 ]]; then
    log "DEBUG: $*"
  fi
}

info() {
  if [[ ${LOGLEVEL} == "INFO" || ${LOGLVL} -ge 3 ]]; then
    log "INFO: $*"
  fi
}

warn() {
  if [[ ${LOGLEVEL} == "WARN" || ${LOGLVL} -ge 2 ]]; then
    log "WARN: $*"
  fi
}

error() {
  if [[ ${LOGLEVEL} == "ERROR" || ${LOGLVL} -ge 1 ]]; then
    log "ERROR: $*"
  fi
}

run() {
  (
    set -x
    "$@"
  )
}

get_script_dir() {
  # https://stackoverflow.com/a/246128
  local SOURCE DIR
  SOURCE="${BASH_SOURCE[0]}"
  while [ -h "$SOURCE" ]; do # resolve $SOURCE until the file is no longer a symlink
    DIR="$(cd -P "$(dirname "$SOURCE")" > /dev/null 2>&1 && pwd)"
    SOURCE="$(readlink "$SOURCE")"
    [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE" # if $SOURCE was a relative symlink, we need to resolve it relative to the path where the symlink file was located
  done
  DIR="$(cd -P "$(dirname "$SOURCE")" > /dev/null 2>&1 && pwd)"
  echo "$DIR"
}

cleanup() {
  info "Cleaning up..."
  info "Done."
}

usage() {
  echo2 "${BASH_SOURCE[0]} [options] {ags...}

  OPTIONS

  -h --help
    Display this message.

  ARGUMENTS

  ags...
    Allgemeiner Gemeinde Schlüssel

  ENVIRONMENT

  LOGLEVEL
    Set to one of DEBUG, INFO, WARN or ERROR to influence the loglevel. Default is WARN.

  LOGLVL
    Numerical equivalent of LOGLEVEL. 1 is ERROR, 2 is WARN, 3 is INFO and 4 is DEBUG.
  "
}

status() {
  local ags="${1:?Please provide an AGS}"
  (
    cd "$(get_script_dir)"
    run poetry run ./corona_status.py "$ags"
  )
}

cmd_status() {
  for ags in "$@"; do
    status "$ags"
  done
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
  : "${LOGLEVEL:=WARN}"
  : "${LOGLVL:=2}"
  case "${1:-}" in
    -h | --h*)
      usage
      ;;
    "")
      usage
      exit 1
      ;;
    *)
      cmd_status "$@"
      ;;
  esac
fi
