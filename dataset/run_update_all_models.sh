#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
PROJECTS_DIR="$(dirname -- "$PROJECT_ROOT")"
PYTHON="$PROJECT_ROOT/venv/bin/python"
MAX_ATTEMPTS=30
RETRY_DELAY_SECONDS=300
export BUILD_FD_DIAGNOSTICS="${BUILD_FD_DIAGNOSTICS:-1}"
exec > >(tee "$SCRIPT_DIR/script_run.log") 2>&1

if [[ ! -x "$PYTHON" ]]; then
    PYTHON="$(command -v python3)"
fi

cd "$PROJECTS_DIR" || exit 1

for ((attempt = 1; attempt <= MAX_ATTEMPTS; attempt++)); do
    echo "Starting update_all_models.py (attempt $attempt/$MAX_ATTEMPTS)"
    if "$PYTHON" -m build.dataset.update_all_models; then
        echo "update_all_models.py completed successfully."
        exit 0
    else
        status=$?
    fi

    if (( attempt == MAX_ATTEMPTS )); then
        echo "update_all_models.py failed on all $MAX_ATTEMPTS attempts." >&2
        exit "$status"
    fi

    echo "Attempt $attempt failed with exit code $status; retrying in $RETRY_DELAY_SECONDS seconds."
    sleep "$RETRY_DELAY_SECONDS"
done
