"""Print commands to recreate the saved components and value chains."""

import json
import re
from build.models.settings import COMPONENTS_DIR, VALUECHAINS_DIR

def print_section(title: str) -> None:
    print("#------------------------------------------")
    print(f"#{title}:")
    print("#------------------------------------------")


def print_components() -> None:
    print_section("Components")
    for path in sorted(COMPONENTS_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        namelist = []
        for listed_company in data.get("listed_companies", []):
            name = listed_company["name"]
            match = re.search(r"\(([A-Za-z])\)$", listed_company.get("key", ""))
            if match:
                name += f"({match.group(1)})"
            namelist.append(name)

        print(
            f"Component.get_item({data['key']!r}, "
            f"namelist={namelist!r})"
        )


def print_valuechains() -> None:
    print_section("ValueChains")
    for path in sorted(VALUECHAINS_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        print("vc = ValueChain.get_item(")
        print(f"    key={data['key']!r},")
        print(f"    component_keys={data.get('component_keys', [])!r},")
        print(")")


if __name__ == "__main__":
    print_components()
    print()
    print_valuechains()
