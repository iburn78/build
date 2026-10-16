from bs4 import BeautifulSoup

from build.tools.render_html import _render_news, _render_qualitative_value


def update_news_html(model, refresh_summary=False):
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
        model.get_news_dir(), type(model).__name__, model.key
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
