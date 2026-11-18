import json
import re
import sys
from contextlib import contextmanager
from collections import defaultdict
import pandas as pd
from build.models.profile import Profile
from build.models.component import Component
from build.models.valuechain import ValueChain
from build.models.segment import Segment
from build.models.settings import (
    PROFILES_DIR,
    COMPONENTS_DIR,
    VALUECHAINS_DIR,
)
from build.tools.tools import df_sector, sector_structure

PROCESS_STEP = 20 

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


def update_unclassified_profiles() -> None:
    """Refresh profiles whose classification row is missing."""
    if "classification" not in df_sector.columns:
        print(
            "Classification column missing; skipping unclassified profiles.",
            file=sys.stderr,
            flush=True,
        )
        return

    # Profile.get_item(parent) refreshes the profile and all of its segments,
    # so collapse segment keys to their parent and avoid duplicate work.
    profile_keys = sorted({
        re.sub(r"\([A-Za-z]\)$", "", str(member_code).strip())
        for member_code, classification in df_sector["classification"].items()
        if pd.isna(classification)
        and str(member_code).strip()
    })
    print(
        f"Unclassified profiles to check: {len(profile_keys)}",
        file=sys.stderr,
        flush=True,
    )

    if not profile_keys:
        return

    total = len(profile_keys)
    for index, key in enumerate(profile_keys, start=1):
        try:
            Profile.get_item(key)
        except Exception as error:
            if _is_fnguide_dns_failure(error):
                print(
                    f"FnGuide DNS resolution failed for {key}; stopping after "
                    f"{index - 1} completed profiles.",
                    file=sys.stderr,
                    flush=True,
                )
                break

            print(f"Skipping {key}: {error}", file=sys.stderr, flush=True)

        if index % PROCESS_STEP == 0 or index == total:
            print(f"({index}/{total}) checked", file=sys.stderr, flush=True)


def _is_fnguide_dns_failure(error: Exception) -> bool:
    message = str(error).lower()
    return (
        "wcomp.fnguide.com" in message
        and (
            "nameresolutionerror" in message
            or "failed to resolve" in message
            or "nodename nor servname" in message
        )
    )


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

    # creating all including valuechain: 0 KRX
    sector_keys = [
        f"{sector['code']} {sector['name']['ko']}"
        for sector in sector_structure.get("sectors", [])
    ]
    ValueChain.get_item(
        key="0 KRX",
        valuechain_keys=sector_keys,
    )


def create_update_from_classification() -> None:
    """Create taxonomy components and nested value chains from df_sector."""
    if "classification" not in df_sector.columns:
        print(
            "Classification column missing; skipping taxonomy models.",
            file=sys.stderr,
            flush=True,
        )
        return

    members_by_subindustry = defaultdict(list)
    for member_code, classification_code in df_sector["classification"].items():
        if pd.isna(classification_code):
            continue
        classification_code = str(classification_code).strip()
        if not classification_code or classification_code.lower() == "nan":
            continue
        members_by_subindustry[classification_code].append(str(member_code).strip())

    for sector in sector_structure.get("sectors", []):
        group_valuechains = []
        for group in sector.get("groups", []):
            industry_valuechains = []
            group_name = f"{group['code']} {group['name']['ko']}"
            for industry in group.get("industries", []):
                industry_components = []
                for subindustry in industry.get("subindustries", []):
                    subindustry_code = str(subindustry.get("code", ""))
                    member_codes = sorted(set(members_by_subindustry.get(subindustry_code, [])))
                    if not member_codes:
                        continue

                    # A profile and its segment rows can share a leaf; represent
                    # that issuer through its segment rows only.
                    segment_parents = {
                        code.rsplit("(", 1)[0]
                        for code in member_codes
                        if re.search(r"\([A-Za-z]\)$", code)
                    }
                    member_codes = [
                        code for code in member_codes
                        if re.search(r"\([A-Za-z]\)$", code) or code not in segment_parents
                    ]
                    component_name = f"{subindustry_code} {subindustry['name']['ko']}"
                    component = Component.get_item(
                        component_name,
                        keylist=member_codes,
                        allow_multiple_segments_per_company=True,
                        _exact_key_only=True,
                    )
                    industry_components.append(component)

                if not industry_components:
                    continue
                industry_name = f"{industry['code']} {industry['name']['ko']}"
                industry_valuechain = ValueChain.get_item(
                    industry_name,
                    components=industry_components,
                    valuechains=[],
                    _exact_key_only=True,
                )
                industry_valuechains.append(industry_valuechain)

            if not industry_valuechains:
                continue
            group_valuechain = ValueChain.get_item(
                group_name,
                components=[],
                valuechains=industry_valuechains,
                _exact_key_only=True,
            )
            group_valuechains.append(group_valuechain)

        if not group_valuechains:
            continue
        sector_name = f"{sector['code']} {sector['name']['ko']}"
        ValueChain.get_item(
            sector_name,
            components=[],
            valuechains=group_valuechains,
            _exact_key_only=True,
        )

    print(
        "Classification-derived components and valuechains refreshed.",
        file=sys.stderr,
        flush=True,
    )


if __name__ == "__main__":

    for i in range(30):
        update_unclassified_profiles()
        time.sleep(300)

    # with _cache_model_items_for_run():
    #     update_profiles()
    #     create_update_from_classification()
    #     update_components() # reuses profiles/segments updated in the first pass
    #     update_valuechains() # reuses components updated in the second pass
