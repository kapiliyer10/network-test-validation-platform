#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT2_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT1_DIR="${PROJECT1_DIR:-$HOME/network-automation-platform}"
PROJECT1_URL="https://github.com/kapiliyer10/network-automation-platform.git"
VENV_DIR="$PROJECT2_ROOT/.venv"
PYTHON_BIN="${PYTHON_BIN:-python3.12}"

log() {
    printf '\n[SETUP] %s\n' "$1"
}

fail() {
    printf '\n[ERROR] %s\n' "$1" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 ||
        fail "Required command '$1' is missing. Install it before continuing."
}

cd "$PROJECT2_ROOT"

log "Checking prerequisites"

require_command "$PYTHON_BIN"
require_command docker
require_command containerlab
require_command git

"$PYTHON_BIN" -c '
import sys
if sys.version_info[:2] != (3, 12):
    raise SystemExit("Python 3.12 is required.")
'

docker info >/dev/null ||
    fail "Docker Engine is not running or is inaccessible."

containerlab version

log "Checking Project 1 repository"

if [[ ! -d "$PROJECT1_DIR" ]]; then
    log "Project 1 was not found. Cloning it into $PROJECT1_DIR"
    git clone --depth 1 "$PROJECT1_URL" "$PROJECT1_DIR"
fi

[[ -d "$PROJECT1_DIR/.git" ]] ||
    fail "$PROJECT1_DIR exists but is not a Git repository. Set PROJECT1_DIR to the correct Project 1 checkout."

PROJECT1_REMOTE="$(git -C "$PROJECT1_DIR" remote get-url origin 2>/dev/null || true)"
PROJECT1_REMOTE="${PROJECT1_REMOTE%.git}"

case "$PROJECT1_REMOTE" in
    "https://github.com/kapiliyer10/network-automation-platform" | \
    "git@github.com:kapiliyer10/network-automation-platform")
        ;;
    *)
        fail "The origin remote in $PROJECT1_DIR is not the expected Project 1 repository."
        ;;
esac

[[ -f "$PROJECT1_DIR/scripts/lab_expanded_up.sh" ]] ||
    fail "Project 1 expanded-lab startup script is missing."

[[ -f "$PROJECT1_DIR/scripts/lab_expanded_down.sh" ]] ||
    fail "Project 1 expanded-lab shutdown script is missing."

[[ -f "$PROJECT1_DIR/topology/srl-expanded.clab.yml" ]] ||
    fail "Project 1 expanded topology definition is missing."

[[ -f "$PROJECT1_DIR/topology/tcp-endpoint/Dockerfile" ]] ||
    fail "Project 1 endpoint Dockerfile is missing."

log "Preparing Project 2 Python environment"

"$PYTHON_BIN" -m venv "$VENV_DIR"

"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -r "$PROJECT2_ROOT/requirements.txt"
"$VENV_DIR/bin/python" -m pip check

log "Building the Linux endpoint image"

docker build \
    -t network-test-endpoint:1.0 \
    "$PROJECT1_DIR/topology/tcp-endpoint"

log "Checking expanded-lab containers"

containers=(
    clab-srl-expanded-R1
    clab-srl-expanded-R2
    clab-srl-expanded-R3
    clab-srl-expanded-H1
    clab-srl-expanded-H2
)

all_containers_running=true

for container in "${containers[@]}"; do
    state="$(docker inspect --format '{{.State.Running}}' "$container" 2>/dev/null || true)"

    if [[ "$state" != "true" ]]; then
        all_containers_running=false
        break
    fi
done

if [[ "$all_containers_running" == "true" ]]; then
    log "All expanded-lab containers are already running. Skipping redeployment."
else
    log "Deploying Project 1 expanded topology"
    "$PROJECT1_DIR/scripts/lab_expanded_up.sh"
fi

log "Waiting for expanded-lab endpoint services"

services_ready=false

for attempt in $(seq 1 60); do
    if docker exec clab-srl-expanded-H1 python3 -c \
        'import socket; s=socket.create_connection(("10.0.24.2", 18080), timeout=2); s.sendall(b"CI_READY"); response=s.recv(128); s.close(); assert response == b"TCP_OK:CI_READY", response' \
        >/dev/null 2>&1 \
        && docker exec clab-srl-expanded-H2 sh -c \
        'ss -lun | grep -q ":18081"' \
        >/dev/null 2>&1 \
        && docker exec clab-srl-expanded-H1 python3 -c \
        'import socket; s=socket.create_connection(("10.0.24.2", 5201), timeout=2); s.close()' \
        >/dev/null 2>&1; then

        services_ready=true
        break
    fi

    printf '[SETUP] Waiting for endpoint services (attempt %s of 60)...\n' "$attempt"
    sleep 5
done

if [[ "$services_ready" != "true" ]]; then
    echo
    echo "Expanded-lab services did not become ready."
    docker ps -a --filter name=clab-srl-expanded
    docker logs clab-srl-expanded-H1 || true
    docker logs clab-srl-expanded-H2 || true
    fail "Endpoint service checks failed. The lab has been left running for diagnosis."
fi

log "Checking router readiness"

cd "$PROJECT2_ROOT"
"$VENV_DIR/bin/python" -m scripts.check_lab_readiness

log "Environment setup completed successfully"

cat <<'SUMMARY'

Project 2 environment is ready.

Activate the virtual environment:
  source .venv/bin/activate

Run unit tests:
  pytest -q -m unit

Run expanded-lab tests:
  pytest -q -m expanded_lab

Run the full regression suite:
  pytest -v

Stop the expanded lab when finished:
  ~/network-automation-platform/scripts/lab_expanded_down.sh

SUMMARY
