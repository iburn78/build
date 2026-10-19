from bs4 import BeautifulSoup

from build.tools.render_html import (
    _render_llm_research,
    _render_news,
    _render_qualitative_value,
)


def update_news_html(model, refresh_summary=False, news_dir=None):
    html_path = model.get_json_path().with_suffix(".html")
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")

    if refresh_summary:
        news_card = next(
            (
                card for card in soup.select(".qualitative-card")
                if (heading := card.select_one(".qualitative-header h4"))
                and heading.get_text(strip=True).lower() == "news"
            ),
            None,
        )
        if news_card:
            content = news_card.select_one(".qualitative-content")
            content.clear()
            fragment = BeautifulSoup(
                _render_qualitative_value(model.news), "html.parser"
            )
            for node in list(fragment.contents):
                content.append(node)

    old_heading = next(
        (
            heading for heading in soup.find_all("h3")
            if heading.get_text(strip=True).lower() == "news"
        ),
        None,
    )
    old_section = soup.select_one(".news-section")
    markup = _render_news(
        news_dir or model.get_news_dir(), type(model).__name__, model.key
    )

    if old_heading:
        if markup:
            fragment = BeautifulSoup(markup, "html.parser")
            new_heading = fragment.find("h3")
            new_section = fragment.select_one(".news-section")
            old_heading.replace_with(new_heading)
            if old_section:
                old_section.replace_with(new_section)
            elif new_section:
                new_heading.insert_after(new_section)
        else:
            old_heading.decompose()
            if old_section:
                old_section.decompose()
    elif markup:
        fragment = BeautifulSoup(markup, "html.parser")
        heading = fragment.find("h3")
        section = fragment.select_one(".news-section")
        qualitative_section = soup.select_one(".qualitative-section")
        if qualitative_section:
            qualitative_section.insert_after(section)
            section.insert_before(heading)

    html_path.write_text(str(soup), encoding="utf-8")


def update_llm_research_html(model):
    """Refresh only the embedded research popup after its Markdown changes."""
    html_path = model.get_json_path().with_suffix(".html")
    if not html_path.is_file():
        return

    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    fragment = BeautifulSoup(
        _render_llm_research(
            model.get_llm_research(),
            model.key,
            show_delete=True,
            updated=getattr(model, "llm_research_updated", ""),
            target_type=type(model).__name__,
        ),
        "html.parser",
    )
    new_row = fragment.select_one(".llm-research-trigger-row")
    new_dialog = fragment.select_one(".llm-research-dialog")
    old_row = soup.select_one(".llm-research-trigger-row")
    old_dialog = soup.select_one(".llm-research-dialog")

    if old_row:
        old_row.replace_with(new_row)
    else:
        legacy_card = soup.select_one(".llm-research-card")
        if legacy_card:
            legacy_card.decompose()
        news_heading = next(
            (heading for heading in soup.find_all("h3")
             if heading.get_text(strip=True).lower() == "news"),
            None,
        )
        if news_heading:
            news_heading.insert_before(new_row)
        else:
            qualitative_section = soup.select_one(".qualitative-section")
            if qualitative_section:
                qualitative_section.insert_after(new_row)

    if old_dialog:
        old_dialog.replace_with(new_dialog)
    elif new_row:
        new_row.insert_after(new_dialog)

    html_path.write_text(str(soup), encoding="utf-8")
