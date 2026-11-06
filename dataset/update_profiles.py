import json
import sys

from build.models.profile import Profile
from build.models.settings import PROFILES_DIR

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

if __name__ == "__main__":
    update_profiles()
