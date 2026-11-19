#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
PROJECTS_DIR="$(dirname -- "$PROJECT_ROOT")"
PYTHON="$PROJECT_ROOT/venv/bin/python"
MAX_ATTEMPTS=30
RETRY_DELAY_SECONDS=300
export BUILD_FD_DIAGNOSTICS="${BUILD_FD_DIAGNOSTICS:-1}"
LOG_FILE="$SCRIPT_DIR/script_run.log"
export LOG_FILE
# Keep the complete, normal run output on screen. The file is a concise
# diagnostic log: failures and tracebacks, run-level progress, and sampled FD
# counts (every 20 profiles, plus whenever the count is near the limit).
: > "$LOG_FILE"
exec > >(tee >(awk '
    function keep(line) {
        print line >> ENVIRON["LOG_FILE"]
        fflush(ENVIRON["LOG_FILE"])
    }
    {
        line = $0

        if (in_traceback) {
            keep(line)
            if (line ~ /^[[:alnum:]_.]*(Error|Exception):/) in_traceback = 0
            next
        }

        if (line ~ /^Traceback \(most recent call last\):/) {
            in_traceback = 1
            keep(line)
            next
        }

        if (line ~ /^(Starting update_all_models\.py|update_all_models\.py completed|update_all_models\.py failed|Attempt [0-9]+ failed|Profiles to check:|Unclassified profiles to check:|Components to check:|Valuechains to check:|Classification column missing|Skipping )/ ||
            line ~ /^\([0-9]+\/[0-9]+\) checked/ ||
            line ~ /(^|[[:space:]])(ERROR|Error|Exception|FAILED|Failed|failure|Failure)(:|[[:space:]]|$)/ ||
            line ~ /too many open files|EMFILE|Task exception was never retrieved|Added banned domain:/ ||
            line ~ /Could not|could not|timed out|Timeout|timeout|ConnectionError|HTTP [45][0-9][0-9]/ {
            keep(line)
            next
        }

        if (line ~ /^\[fd\]/) {
            if (line ~ /open \(soft limit/ && line ~ /: [0-9]+ open/) {
                count = line
                sub(/^.*: /, "", count)
                sub(/ open.*/, "", count)
                if (count + 0 >= 200) {
                    keep(line)
                    next
                }
            }
            if (line ~ /profile [0-9]+\//) {
                label = line
                sub(/^.*profile /, "", label)
                sub(/\/.*/, "", label)
                if ((label + 0) == 1 || (label + 0) % 20 == 0) keep(line)
            }
        }
    }
' ))) 2>&1

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
