import json
import sys

from build.models.profile import Profile
from build.models.component import Component
from build.models.valuechain import ValueChain
from build.models.settings import (
    PROFILES_DIR,
    COMPONENTS_DIR,
    VALUECHAINS_DIR,
)

PROCESS_STEP = 20

def update_profiles() -> None:
    paths = sorted(PROFILES_DIR.glob("*.json"))
    total = len(paths)
    print(f"Profiles to check: {total}", file=sys.stderr, flush=True)

    for index, path in enumerate(paths, start=1):
        data = json.loads(path.read_text(encoding="utf-8"))
        key = data["key"]
        Profile.get_item(key)
        if index % PROCESS_STEP == 0 or index == total:
            print(f"({index}/{total}) checked", file=sys.stderr, flush=True)


def update_components() -> None:
    paths = sorted(COMPONENTS_DIR.glob("*.json"))
    total = len(paths)
    print(f"Components to check: {total}", file=sys.stderr, flush=True)

    for index, path in enumerate(paths, start=1):
        data = json.loads(path.read_text(encoding="utf-8"))
        Component.get_item(data["key"])
        if index % PROCESS_STEP == 0 or index == total:
            print(f"({index}/{total}) checked", file=sys.stderr, flush=True)


def update_valuechains() -> None:
    paths = sorted(VALUECHAINS_DIR.glob("*.json"))
    total = len(paths)
    print(f"Valuechains to check: {total}", file=sys.stderr, flush=True)

    for index, path in enumerate(paths, start=1):
        data = json.loads(path.read_text(encoding="utf-8"))
        ValueChain.get_item(data["key"])
        if index % PROCESS_STEP == 0 or index == total:
            print(f"({index}/{total}) checked", file=sys.stderr, flush=True)


if __name__ == "__main__":
    update_profiles()
    update_components()
    update_valuechains()
