import json
import re
import sys

from build.tools.tools import ListedCompany
from build.models.profile import Profile


def resolve_listed_company(query: str) -> ListedCompany:
    if re.fullmatch(r"\d+", query):
        try:
            return ListedCompany.from_key(query)
        except ValueError:
            raise LookupError(f"No public company matches code ‘{query}’.") from None

    try:
        listed_company = ListedCompany.from_name(query)
    except ValueError as error:
        if str(error).startswith("Ambiguous company name"):
            raise LookupError(
                f"More than one public company matches ‘{query}’. Enter the exact company name or code."
            ) from None
        raise LookupError(
            f"No search result or public company found for ‘{query}’."
        ) from None

    if listed_company.name.casefold() != query.casefold():
        raise LookupError(
            f"No exact public company name matched ‘{query}’. Try the official name or code."
        )
    return listed_company


def get_profile(query: str) -> dict:
    query = query.strip()
    if not query:
        return {"ok": False, "error": "Enter a company name or code."}

    try:
        listed_company = resolve_listed_company(query)
    except LookupError as error:
        return {"ok": False, "error": str(error)}

    try:
        profile = Profile.get_item(listed_company.key)
    except Exception:
        import traceback

        traceback.print_exc(file=sys.stdout)
        return {
            "ok": False,
            "error": f"‘{listed_company.name}’ matched, but its profile could not be created. Try again later.",
        }

    return {
        "ok": True,
        "key": profile.code,
        "name": profile.name,
        "file": f"{profile.filename}.html",
    }


if __name__ == "__main__":
    try:
        result = get_profile(json.load(sys.stdin).get("query", ""))
    except Exception as error:
        import traceback

        traceback.print_exc(file=sys.stdout)
        result = {"ok": False, "error": "The company lookup could not be completed."}

    with open(3, "w", encoding="utf-8", closefd=False) as response_pipe:
        response_pipe.write(json.dumps(result, ensure_ascii=False))
    if not result.get("ok"):
        sys.exit(1)
