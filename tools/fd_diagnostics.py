"""Optional process file-descriptor diagnostics for long-running updates."""

import os
import sys


def log_open_fds(stage: str) -> None:
    """Log the current open descriptor count when diagnostics are enabled."""
    if os.getenv("BUILD_FD_DIAGNOSTICS", "").strip().lower() not in {
        "1", "true", "yes", "on"
    }:
        return

    fd_directory = "/dev/fd" if sys.platform == "darwin" else "/proc/self/fd"
    try:
        count = len(os.listdir(fd_directory))
    except OSError as error:
        print(f"[fd] {stage}: count unavailable: {error}", file=sys.stderr, flush=True)
        return

    try:
        import resource

        soft_limit, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
    except (ImportError, AttributeError, OSError, ValueError):
        soft_limit = "unknown"

    print(f"[fd] {stage}: {count} open (soft limit {soft_limit})", file=sys.stderr, flush=True)
