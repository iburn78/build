"""LLM-assisted grouping of company profiles by business similarity."""
from __future__ import annotations

import json
import math
from pathlib import Path
import pandas as pd
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from build.models.component import Component, Traits
from build.models.profile import Profile
from build.models.settings import (
    MIN_PROFILES_IN_GROUPING,
    MIN_MARCAP_IN_GROUPING,
    PROFILE_GROUPING_LLM,
    REFS_DIR,
    llm_selector,
    PROFILE_GROUPING_JSON_FILE,
)
from build.models.valuechain import ValueChain


class ProfileGroup(BaseModel):
    label: str = Field(description="Short name for the shared business activity")
    rationale: str = Field(description="Why these profiles belong together")
    profile_codes: list[str] = Field(description="Stock codes of group members")
    is_unclassified: bool = Field(
        default=False,
        description="True only for the shared group of profiles that cannot be classified into a business group",
    )


class ProfileGrouping(BaseModel):
    groups: list[ProfileGroup]
    sector: str = Field(default="", exclude=True)
    subsector: str = Field(default="", exclude=True)
    sector_code: str = Field(default="", exclude=True)
    subsector_code: str = Field(default="", exclude=True)


def _load_krics_map() -> pd.DataFrame:
    workbooks = sorted(
        REFS_DIR.glob("krics_*.xlsx"),
        key=lambda path: path.stat().st_mtime,
    )
    if not workbooks:
        raise FileNotFoundError(f"No KRICS Excel map found in {REFS_DIR}.")
    return pd.read_excel(
        workbooks[-1],
        dtype={"code": str, "sector_code": str, "subsector_code": str},
    )


def _filter_krics_map(
    sector_map: pd.DataFrame,
    sector: str | None = None,
    subsector: str | None = None,
    sector_code: str | None = None,
    subsector_code: str | None = None,
) -> pd.DataFrame:
    for column, value in (
        ("sector", sector),
        ("subsector", subsector),
        ("sector_code", sector_code),
        ("subsector_code", subsector_code),
    ):
        if value is not None:
            sector_map = sector_map[sector_map[column] == str(value).strip()]
    if sector_map.empty:
        raise ValueError("No KRICS profiles match the requested sector/subsector filters.")
    return sector_map


def _make_agent() -> Agent[None, str]:
    base_url, api_key, model_name = llm_selector(PROFILE_GROUPING_LLM)
    client = AsyncOpenAI(base_url=base_url, api_key=api_key)
    provider = OpenAIProvider(openai_client=client)
    model = OpenAIChatModel(model_name=model_name, provider=provider)
    return Agent(model=model, output_type=str)


_GROUPING_AGENT = _make_agent()


def _classification(profile: Profile) -> tuple[str, str, str, str]:
    meta = (profile.financials or {}).get("meta", {})
    classification = meta.get("classification") or {}
    return (
        str(classification.get("sector") or "Unclassified"),
        str(classification.get("subsector") or "Unclassified"),
        str(classification.get("sector_code") or ""),
        str(classification.get("subsector_code") or ""),
    )


def _profile_input(profile: Profile) -> dict:
    overview = profile.overview.model_dump(mode="json")
    business = profile.info_section.model_dump(mode="json")
    return {
        "code": str(profile.code),
        "name": profile.name,
        "overview": overview,
        "business": business,
    }


def _profile_marcap_krw(profile: Profile) -> float:
    """Return the latest saved profile market cap in KRW."""
    financials = profile.financials or {}
    try:
        marcap = float(financials["shape"]["financials"]["marcap"])
        unit = float(financials["meta"]["unit"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            f"Profile {profile.code} has no usable latest market cap or unit. "
            "Refresh the profile before grouping."
        ) from error
    value = marcap * unit
    if not math.isfinite(value):
        raise ValueError(f"Profile {profile.code} has a non-finite latest market cap.")
    return value


def _run_grouping(prompt: str) -> ProfileGrouping:
    response = _GROUPING_AGENT.run_sync(prompt).output.strip()
    if response.startswith("```"):
        response = response.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return ProfileGrouping.model_validate_json(response)


def _validate_assignments(result: ProfileGrouping, profiles: list[Profile]) -> None:
    expected = [str(profile.code) for profile in profiles]
    expected_set = set(expected)
    aliases: dict[str, set[str]] = {}
    for code in expected:
        normalized = code.strip().upper()
        aliases.setdefault(normalized, set()).add(code)
        if normalized.isdigit():
            aliases.setdefault(normalized.lstrip("0") or "0", set()).add(code)

    for group in result.groups:
        normalized_codes = []
        for raw_code in group.profile_codes:
            code = str(raw_code).strip().upper()
            if code.endswith(".0"):
                code = code[:-2]
            candidates = aliases.get(code, set())
            normalized_codes.append(next(iter(candidates)) if len(candidates) == 1 else code)
        group.profile_codes = normalized_codes

    assigned = [code for group in result.groups for code in group.profile_codes]
    assigned_set = set(assigned)
    missing = sorted(expected_set - assigned_set)
    unexpected = sorted(assigned_set - expected_set)
    if len(assigned) != len(assigned_set) or missing or unexpected:
        raise ValueError(
            "LLM grouping must assign every input profile code exactly once. "
            f"Missing: {missing[:10]}; unexpected: {unexpected[:10]}; "
            f"duplicate assignments: {len(assigned) - len(assigned_set)}."
        )


def _is_unclassified_label(label: str) -> bool:
    normalized = "".join(char for char in label.casefold() if char.isalnum())
    return any(term in normalized for term in (
        "unclassified", "unclassifiable", "uncategorized", "unassigned",
        "미분류", "분류안됨", "분류되지않", "분류불가",
    ))


def _is_unclassified_group(group: ProfileGroup) -> bool:
    return group.is_unclassified or _is_unclassified_label(group.label)


def _canonicalize_unclassified_groups(result: ProfileGrouping) -> None:
    for group in result.groups:
        if _is_unclassified_group(group):
            group.label = "unclassified"
            group.is_unclassified = True


def _reuse_saved_group_labels(result: ProfileGrouping, saved_groups: dict) -> None:
    """Keep component identities stable when reruns find the same member clusters."""
    old_members = {
        label: set(map(str, details.get("profiles", [])))
        | set(map(str, details.get("small_cap", [])))
        for label, details in saved_groups.items()
        if not _is_unclassified_label(label) and label.casefold() != "small_cap"
    }
    candidates = []
    for group_index, group in enumerate(result.groups):
        if _is_unclassified_group(group):
            continue
        new_members = set(map(str, group.profile_codes))
        for label, members in old_members.items():
            overlap = len(new_members & members)
            minimum_overlap = min(2, len(new_members), len(members))
            union = len(new_members | members)
            if overlap >= minimum_overlap and union and overlap / union >= 0.25:
                candidates.append((overlap / union, overlap, group_index, label))

    used_groups = set()
    used_labels = set()
    current_label_owners = {
        group.label: index for index, group in enumerate(result.groups)
    }
    for _, _, group_index, label in sorted(candidates, reverse=True):
        if group_index in used_groups or label in used_labels:
            continue
        if label in current_label_owners and current_label_owners[label] != group_index:
            continue
        result.groups[group_index].label = label
        used_groups.add(group_index)
        used_labels.add(label)


def _run_validated_grouping(prompt: str, profiles: list[Profile]) -> ProfileGrouping:
    result = _run_grouping(prompt)
    try:
        _validate_assignments(result, profiles)
    except ValueError as error:
        correction_prompt = f"""Correct the profile codes in this grouping.
The previous response did not assign all input profile codes exactly once.
Use only codes from the original input, preserving every leading zero. Keep the proposed groups where possible.
Use the exact label "unclassified" and set is_unclassified to true for any shared unclassified group. Return only corrected JSON in the same schema.

Validation issue: {error}
Previous response:
{json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2)}

Original task and input:
{prompt}"""
        result = _run_grouping(correction_prompt)
        _validate_assignments(result, profiles)
    return result


def group_profiles(profiles: list[Profile]) -> list[ProfileGrouping]:
    """Group profiles by business similarity, separately per sector/subsector."""
    if not profiles:
        raise ValueError("At least one profile is required for grouping.")

    partitions: dict[tuple[str, str, str, str], list[Profile]] = {}
    for profile in profiles:
        partitions.setdefault(_classification(profile), []).append(profile)

    try:
        saved_grouping_json = Path(PROFILE_GROUPING_JSON_FILE)
        saved_grouping = (
            json.loads(saved_grouping_json.read_text(encoding="utf-8"))
            if saved_grouping_json.is_file()
            else {}
        )
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid profile grouping JSON: {saved_grouping_json}") from error

    results = []
    for (sector, subsector, sector_code, subsector_code), category_profiles in sorted(partitions.items()):
        request = {
            "sector": sector,
            "subsector": subsector,
            "sector_code": sector_code,
            "subsector_code": subsector_code,
            "profiles": [_profile_input(profile) for profile in category_profiles],
        }
        prompt = f"""Group these Korean listed-company profiles by similarity of their actual businesses.
Only compare companies within the supplied sector and subsector. Do not create groups across categories.
Use overview and business information; segments, products, and services are evidence, not group names by themselves.
Create a concise Korean label and rationale for each group. Aim for at least {MIN_PROFILES_IN_GROUPING} profiles per group. Do not create a "small_cap" group; small-cap profiles will be separated after grouping.
Avoid singleton and two-profile groups. Try to combine them with the most similar larger group based on actual business activities.
Use one unclassified group for profiles that cannot reasonably fit any larger group; do not create a separate unclassified group for each profile.
Assign every supplied profile code exactly once. Copy codes exactly, including leading zeros. Do not invent codes or force clearly unrelated businesses together.
Use the exact label "unclassified" for any shared group of profiles that cannot be classified into a business group, and set its is_unclassified field to true. Do not use Korean synonyms or alternate labels for this group.
Return only valid JSON matching this shape:
{{"groups": [{{"label": "...", "rationale": "...", "profile_codes": ["..."], "is_unclassified": false}}]}}

Input JSON:
{json.dumps(request, ensure_ascii=False, indent=2)}"""
        result = _run_validated_grouping(prompt, category_profiles)
        if any(len(group.profile_codes) < MIN_PROFILES_IN_GROUPING for group in result.groups):
            refinement_prompt = f"""Refine this grouping of Korean listed-company profiles within {sector} / {subsector}.
The preferred minimum group size is {MIN_PROFILES_IN_GROUPING}. Merge undersized groups into the most similar larger group when their actual businesses are reasonably related.
If a profile truly does not fit any larger group, put it in one shared unclassified group instead of making a singleton group.
Do not create groups smaller than {MIN_PROFILES_IN_GROUPING}, except for that one unclassified group if necessary. Do not create a "small_cap" group; small-cap profiles will be separated after grouping.
Use the exact label "unclassified" and set is_unclassified to true for any shared unclassified group. Do not use Korean synonyms or alternate labels.
Assign every supplied profile code exactly once. Copy codes exactly, including leading zeros. Do not invent codes. Return only valid JSON matching this shape:
{{"groups": [{{"label": "...", "rationale": "...", "profile_codes": ["..."], "is_unclassified": false}}]}}

Profiles:
{json.dumps(request, ensure_ascii=False, indent=2)}

Proposed groups:
{json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2)}"""
            result = _run_validated_grouping(refinement_prompt, category_profiles)

        _canonicalize_unclassified_groups(result)
        if any(group.label.strip().casefold().replace("-", "_").replace(" ", "_") == "small_cap" for group in result.groups):
            raise ValueError('"small_cap" is reserved for profiles below the market-cap threshold.')

        # Gather any remaining small clusters into one unclassified group.
        unclassified_codes = [
            code
            for group in result.groups
            if len(group.profile_codes) < MIN_PROFILES_IN_GROUPING
            for code in group.profile_codes
        ]
        if unclassified_codes:
            result.groups = [
                group for group in result.groups
                if len(group.profile_codes) >= MIN_PROFILES_IN_GROUPING
            ]
            result.groups.append(ProfileGroup(
                label=(
                    "unclassified"
                ),
                rationale="These profiles could not be confidently combined with a larger business group.",
                profile_codes=unclassified_codes,
                is_unclassified=True,
            ))
        saved_groups = (
            saved_grouping.get(sector, {})
            .get("subsectors", {})
            .get(subsector, {})
            .get("groups", {})
        )
        _reuse_saved_group_labels(result, saved_groups)
        results.append(result)
        print(f"\n[{sector} / {subsector}]")
        for group in result.groups:
            members = [
                f"{profile.name} ({profile.code})"
                for profile in category_profiles
                if str(profile.code) in group.profile_codes
            ]
            print(f"- {group.label}: {', '.join(members)}")
            print(f"  {group.rationale}")
    return results


def create_components(groupings: list[ProfileGrouping]) -> list[Component]:
    """Create or update one Component per group, using its label and rationale."""
    components = []
    labels = set()
    for grouping in groupings:
        for group in grouping.groups:
            if _is_unclassified_group(group):
                group.label = "unclassified"
                group.is_unclassified = True
                print(f"Skipped unclassified group {group.label}: not creating a component")
                continue
            if group.label in labels:
                raise ValueError(f"Duplicate component label in groupings: {group.label}")
            if not group.profile_codes:
                raise ValueError(f"Cannot create component {group.label!r} without profiles.")
            eligible_codes = [
                str(code)
                for code in group.profile_codes
                if _profile_marcap_krw(Profile.get_item(str(code))) >= MIN_MARCAP_IN_GROUPING
            ]
            if not eligible_codes:
                print(f"Skipped {group.label}: all profiles are below the market-cap threshold")
                continue
            labels.add(group.label)
            component = Component.get_item(
                group.label,
                keylist=eligible_codes,
                info_section=_component_info_section(group.label, group.rationale),
            )
            components.append(component)
            print(f"Created/updated component {group.label}: {len(eligible_codes)} profiles")
    return components


def krics_prepare_profiles(
    sector: str | None = None,
    subsector: str | None = None,
    sector_code: str | None = None,
    subsector_code: str | None = None,
) -> list[Profile]:
    """Create or refresh profiles for all KRICS companies matching the filters."""
    sector_map = _filter_krics_map(
        _load_krics_map(), sector, subsector, sector_code, subsector_code
    )
    profiles = []
    for row in sector_map.drop_duplicates("code").itertuples(index=False):
        profile = Profile.get_item(str(row.code))
        meta = (profile.financials or {}).setdefault("meta", {})
        meta["classification"] = {
            "sector": row.sector,
            "subsector": row.subsector,
            "sector_code": row.sector_code,
            "subsector_code": row.subsector_code,
        }
        profiles.append(profile)
    print(f"Prepared {len(profiles)} KRICS profiles.")
    return profiles


def _save_groupings(
    groupings: list[ProfileGrouping],
    marcap_by_code: dict[str, float],
) -> dict:
    """Replace the grouped subsector records while retaining unrelated records."""
    path = Path(PROFILE_GROUPING_JSON_FILE)
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid profile grouping JSON: {path}") from error
    if not isinstance(data, dict):
        raise ValueError(f"Profile grouping JSON must contain an object: {path}")

    for grouping in groupings:
        sector = grouping.sector
        subsector = grouping.subsector
        sector_code = grouping.sector_code
        subsector_code = grouping.subsector_code
        old_sector = data.get(str(sector), {})
        old_subsector = old_sector.get("subsectors", {}).get(str(subsector), {})
        old_groups = old_subsector.get("groups", {})
        new_labels = {group.label for group in grouping.groups}
        for deleted_label in set(old_groups) - new_labels:
            old_key = _component_key(sector_code, subsector_code, deleted_label)
            if Component._get_json_path_from_prefix(old_key):
                from build.tools.delete_instance import delete_instance

                delete_instance({"objectType": "Component", "objectId": old_key})
        persisted_groups = {}
        for group in grouping.groups:
            eligible_codes = []
            small_cap_codes = []
            for code in group.profile_codes:
                if marcap_by_code[str(code)] < MIN_MARCAP_IN_GROUPING:
                    small_cap_codes.append(str(code))
                else:
                    eligible_codes.append(str(code))
            persisted_groups[group.label] = {
                "profiles": eligible_codes,
                "rationale": group.rationale,
                "small_cap": small_cap_codes,
            }
        new_subsector = {
            "subsector_code": str(subsector_code),
            "groups": persisted_groups,
        }
        existing_sector = data.setdefault(str(sector), {"sector_code": str(sector_code), "subsectors": {}})
        existing_sector["sector_code"] = str(sector_code)
        existing_sector.setdefault("subsectors", {})[str(subsector)] = new_subsector

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def _component_key(sector_code: str, subsector_code: str, group_label: str) -> str:
    return f"{sector_code}{subsector_code} {group_label}"


def _component_info_section(key: str, rationale: str) -> Traits | None:
    """Keep saved component traits on updates; seed rationale only when needed."""
    path = Component._get_json_path_from_prefix(key)
    if path is None:
        return Traits(notes=rationale)
    existing = Component._load_from_path(path)
    if existing is None:
        # Let get_item recover any reviewed information from invalid JSON.
        return None
    info_section = existing.info_section.model_copy(deep=True)
    if not info_section.reviewed:
        info_section.notes = rationale
    return info_section


def _select_grouping_subsectors(
    data: dict,
    sector: str | None,
    subsector: str | None,
    sector_code: str | None,
    subsector_code: str | None,
) -> list[tuple[str, dict, str, dict]]:
    if subsector is None and subsector_code is None:
        raise ValueError("A subsector name or subsector_code is required.")
    matches = []
    for sector_name, sector_data in data.items():
        if sector is not None and sector_name != str(sector).strip():
            continue
        if sector_code is not None and str(sector_data.get("sector_code")) != str(sector_code).strip():
            continue
        for subsector_name, subsector_data in sector_data.get("subsectors", {}).items():
            if subsector is not None and subsector_name != str(subsector).strip():
                continue
            if subsector_code is not None and str(subsector_data.get("subsector_code")) != str(subsector_code).strip():
                continue
            matches.append((sector_name, sector_data, subsector_name, subsector_data))
    if not matches:
        raise ValueError("No saved profile grouping matches the requested sector/subsector.")
    if len(matches) > 1:
        raise ValueError("Grouping filters match multiple subsectors; specify sector or codes.")
    return matches


def krics_create_components(
    sector: str | None = None,
    subsector: str | None = None,
    sector_code: str | None = None,
    subsector_code: str | None = None,
) -> list[Component]:
    """Create/update components and their sector valuechain from saved groupings."""
    if not Path(PROFILE_GROUPING_JSON_FILE).is_file():
        raise FileNotFoundError(f"No saved profile groupings found: {PROFILE_GROUPING_JSON_FILE}")
    data = json.loads(Path(PROFILE_GROUPING_JSON_FILE).read_text(encoding="utf-8"))
    matches = _select_grouping_subsectors(data, sector, subsector, sector_code, subsector_code)
    components = []
    for sector_name, sector_data, subsector_name, subsector_data in matches:
        group_keys = []
        for group_label, group_data in subsector_data.get("groups", {}).items():
            if _is_unclassified_label(group_label) or group_label.casefold() == "small_cap":
                continue
            profile_codes = group_data.get("profiles", [])
            if not profile_codes:
                key = _component_key(
                    str(sector_data["sector_code"]),
                    str(subsector_data["subsector_code"]),
                    group_label,
                )
                component_path = Component._get_json_path_from_prefix(key)
                if component_path:
                    from build.tools.delete_instance import delete_instance

                    delete_instance({"objectType": "Component", "objectId": key})
                continue
            key = _component_key(
                str(sector_data["sector_code"]),
                str(subsector_data["subsector_code"]),
                group_label,
            )
            component = Component.get_item(
                key=key,
                keylist=profile_codes,
                info_section=_component_info_section(key, group_data.get("rationale", "")),
            )
            components.append(component)
            group_keys.append(component.key)
            print(f"Created/updated component {component.key}: {len(profile_codes)} profiles")

        # Enrich the sector valuechain with components already created from all
        # saved subsectors. This lets callers build it incrementally.
        sector_components = set()
        for saved_subsector_name, saved_subsector in sector_data.get("subsectors", {}).items():
            for group_label in saved_subsector.get("groups", {}):
                if _is_unclassified_label(group_label) or group_label.casefold() == "small_cap":
                    continue
                if not saved_subsector.get("groups", {}).get(group_label, {}).get("profiles"):
                    continue
                key = _component_key(
                    str(sector_data["sector_code"]),
                    str(saved_subsector.get("subsector_code", "")),
                    group_label,
                )
                if Component._get_json_path_from_prefix(key):
                    sector_components.add(key)
        if sector_components:
            valuechain_key = f"{sector_data['sector_code']}00 {sector_name}"
            ValueChain.get_item(
                key=valuechain_key,
                component_keys=sorted(sector_components),
            )
    return components


def krics_group_profiles(
    sector: str | None = None,
    subsector: str | None = None,
    sector_code: str | None = None,
    subsector_code: str | None = None,
) -> list[ProfileGrouping]:
    """Group existing profiles, print the result, and persist it to the KRICS JSON."""
    sector_map = _filter_krics_map(
        _load_krics_map(), sector, subsector, sector_code, subsector_code
    )

    profiles = []
    missing = []
    for row in sector_map.drop_duplicates("code").itertuples(index=False):
        code = str(row.code)
        path = Profile._get_json_path_from_prefix(code)
        profile = Profile._load_from_path(path) if path else None
        if profile is None:
            missing.append(code)
            continue
        # Use the selected KRICS workbook as the category source for this run.
        meta = (profile.financials or {}).setdefault("meta", {})
        meta["classification"] = {
            "sector": row.sector,
            "subsector": row.subsector,
            "sector_code": row.sector_code,
            "subsector_code": row.subsector_code,
        }
        profiles.append(profile)

    if missing:
        raise ValueError(
            "Profiles must be prepared before grouping. Missing or unreadable codes: "
            + ", ".join(missing)
            + ". Run krics_prepare_profiles() first."
        )
    if not profiles:
        raise ValueError("No existing readable profiles matched the KRICS filters.")
    groupings = group_profiles(profiles)
    # The grouping pass partitions by KRICS metadata, so map each result back to
    # the fixed names and codes from the workbook before replacing the JSON entry.
    categories = (
        sector_map[["sector", "subsector", "sector_code", "subsector_code"]]
        .drop_duplicates()
    )
    by_codes = {
        (str(row.sector_code), str(row.subsector_code)): row
        for row in categories.itertuples(index=False)
    }
    for grouping in groupings:
        sample = next(
            profile for profile in profiles
            if str(profile.code) in {code for group in grouping.groups for code in group.profile_codes}
        )
        meta = (sample.financials or {}).get("meta", {}).get("classification", {})
        row = by_codes[(str(meta.get("sector_code", "")), str(meta.get("subsector_code", "")))]
        grouping.sector = str(row.sector)
        grouping.subsector = str(row.subsector)
        grouping.sector_code = str(row.sector_code)
        grouping.subsector_code = str(row.subsector_code)
    marcap_by_code = {str(profile.code): _profile_marcap_krw(profile) for profile in profiles}
    small_cap_count = sum(value < MIN_MARCAP_IN_GROUPING for value in marcap_by_code.values())
    if small_cap_count:
        print(
            f"Moved {small_cap_count} profiles below the "
            f"{MIN_MARCAP_IN_GROUPING:,} KRW market-cap threshold to small_cap."
        )
    _save_groupings(groupings, marcap_by_code)
    return groupings

if __name__ == "__main__":
    krics_prepare_profiles(sector_code='10', subsector_code='10')
    krics_group_profiles(sector_code='10', subsector_code='10')
    krics_create_components(sector_code='10', subsector_code='10')
