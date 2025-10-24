#!/usr/bin/env bash
# Helper to launch the Cloud SQL Auth Proxy for the optcom-postgres instance.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROXY_BIN="${SCRIPT_DIR}/cloud-sql-proxy"

if [[ ! -x "${PROXY_BIN}" ]]; then
  echo "❌ Proxy binary not found at ${PROXY_BIN}. Run setup again." >&2
  exit 1
fi

INSTANCE_CONNECTION_NAME=${INSTANCE_CONNECTION_NAME:-crafty-water-453519-d7:europe-west4:optcom-postgres}
PROXY_PORT=${PROXY_PORT:-5433}
BIND_ADDR=${BIND_ADDR:-127.0.0.1}
CREDENTIALS_FILE=${GOOGLE_APPLICATION_CREDENTIALS:-}

# Allow simple override via .env-style file if present
ENV_FILE="${SCRIPT_DIR}/proxy.env"
if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  INSTANCE_CONNECTION_NAME=${INSTANCE_CONNECTION_NAME:-${INSTANCE_CONNECTION_NAME}}
  PROXY_PORT=${PROXY_PORT:-${PROXY_PORT}}
  BIND_ADDR=${BIND_ADDR:-${BIND_ADDR}}
  if [[ -z "${CREDENTIALS_FILE}" && -n "${GOOGLE_APPLICATION_CREDENTIALS:-}" ]]; then
    CREDENTIALS_FILE=${GOOGLE_APPLICATION_CREDENTIALS}
  fi
fi

echo "🚀 Starting Cloud SQL Proxy"
echo "   Instance : ${INSTANCE_CONNECTION_NAME}"
echo "   Listen   : ${BIND_ADDR}:${PROXY_PORT}"

ARGS=(-instances="${INSTANCE_CONNECTION_NAME}=tcp:${BIND_ADDR}:${PROXY_PORT}")

if [[ -n "${CREDENTIALS_FILE}" ]]; then
  echo "   Auth     : service account (${CREDENTIALS_FILE})"
  ARGS+=(-credential_file="${CREDENTIALS_FILE}")
else
  echo "   Auth     : gcloud CLI active account"
  echo "             (run 'gcloud auth login' if you haven't already)"
fi

echo
exec "${PROXY_BIN}" "${ARGS[@]}"
