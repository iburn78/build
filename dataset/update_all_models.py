import json
import re
import sys
from contextlib import contextmanager

from build.models.profile import Profile
from build.models.component import Component
from build.models.valuechain import ValueChain
from build.models.segment import Segment
from build.models.settings import (
    PROFILES_DIR,
    COMPONENTS_DIR,
    VALUECHAINS_DIR,
)
@contextmanager
def _cache_model_items_for_run():
    """Reuse model instances across this script's profile/component/value-chain passes."""
    cache = {}
    model_classes = (Profile, Segment, Component, ValueChain)
    original_descriptors = {
        model_class: model_class.__dict__.get("get_item")
        for model_class in model_classes
    }

    for model_class in model_classes:
        original_get_item = model_class.get_item

        def make_cached_get_item(cls, original):
            def cached_get_item(model_cls, key, *args, **kwargs):
                normalized_key = str(key).strip()
                if model_cls is Profile:
                    normalized_key = re.sub(r"\([A-Za-z]\)$", "", normalized_key)
                cache_key = (model_cls, normalized_key.casefold())
                if cache_key not in cache:
                    cache[cache_key] = original(key, *args, **kwargs)
                return cache[cache_key]

            return classmethod(cached_get_item)

        setattr(model_class, "get_item", make_cached_get_item(model_class, original_get_item))

    try:
        yield
    finally:
        for model_class, descriptor in original_descriptors.items():
            if descriptor is None:
                delattr(model_class, "get_item")
            else:
                setattr(model_class, "get_item", descriptor)

PROCESS_STEP = 20

def update_profiles() -> None:
    profile_items = []
    for path in sorted(PROFILES_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        # Segment JSONs live in PROFILES_DIR too. Profile.get_item(segment_key)
        # resolves back to the parent profile and rebuilds every segment, so
        # processing those files here repeats the same work.
        if "profile_code" in data and "segment_name" in data:
            continue
        profile_items.append((path, data))

    total = len(profile_items)
    print(f"Profiles to check: {total}", file=sys.stderr, flush=True)

    for index, (_path, data) in enumerate(profile_items, start=1):
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
    with _cache_model_items_for_run():
        update_profiles()
        update_components() # reuses profiles/segments updated in the first pass
        update_valuechains() # reuses components updated in the second pass
