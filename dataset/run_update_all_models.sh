#!/bin/bash

PROJECT_DIR="/Users/andy/projects/build"
VENV_DIR="$PROJECT_DIR/venv"
LOG_DIR="$PROJECT_DIR/dataset/logs"
LOG_FILE="$LOG_DIR/update_all_models.log"

mkdir -p "$LOG_DIR"

{
    printf '\n[%s] Starting update_all_models\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')"
    cd "$PROJECT_DIR" || exit 1
    source "$VENV_DIR/bin/activate" || exit 1

    printf '[%s] Running git pull\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')"
    git pull
    pull_status=$?
    if [ "$pull_status" -ne 0 ]; then
        printf '[%s] git pull failed with exit code %s; continuing with model update\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')" "$pull_status"
    fi

    printf '[%s] Running update_all_models\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')"
    python -u -m dataset.update_all_models
    update_status=$?

    printf '[%s] Running git push\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')"
    git push
    push_status=$?
    if [ "$push_status" -ne 0 ]; then
        printf '[%s] git push failed with exit code %s\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')" "$push_status"
    fi

    printf '[%s] update_all_models finished with exit code %s (git pull: %s, git push: %s)\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')" "$update_status" "$pull_status" "$push_status"
    if [ "$update_status" -ne 0 ]; then
        exit "$update_status"
    fi
    if [ "$pull_status" -ne 0 ] || [ "$push_status" -ne 0 ]; then
        exit 1
    fi
    exit 0
} >> "$LOG_FILE" 2>&1


# cron 
# 30 23 * * 1-5 /Users/andy/projects/build/dataset/run_update_all_models.sh