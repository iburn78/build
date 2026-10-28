import requests
import hashlib
import math
from html import escape
from datetime import datetime
from build.tools.tools import get_FN_GUIDE_url, get_NAVER_url
from build.models.settings import QUARTERLY_PERFORMANCES_URL, INDEX_HTML, BASE_DATA_DIR
from build.models.settings import TEMPLATE_HTML, COLLAPSED_PATHS, NO_CHART_KEYS 
from pydantic import BaseModel
from pathlib import Path
from markdown_it import MarkdownIt

# can use full path or key_only
DISPLAY_KEY_DICT = {
    "shape.financials": "financials (in unit)",
    "-m_rank": "(rank)",
    "-r_rank": "(rank)",
    "-o_rank": "(rank)",
    "assess_data.opincome.slope": "slope (qtr, in unit)",
    "indplot_period": "indplot_period (within the group)",
    "alpha(%)": "alpha (%, daily)",
    "assess_result.volatility_level": 'volatility (measure)',
    "assess_result.amount_level": 'amount (measure)',
    "assess_result.alpha_level": 'alpha (measure)',
}

year = str(datetime.today().year)

def _fmt_value(key, value):
    if value is None:
        return "-"

    if isinstance(value, str) and value.strip().lower() in {
        "nan", "inf", "-inf", "infinity", "-infinity"
    }:
        return "-"

    if not isinstance(value, (bool, str)):
        try:
            if not math.isfinite(float(value)):
                return "-"
        except (TypeError, ValueError, OverflowError):
            pass

    if isinstance(value, bool):
        return (
            '<span class="true_bool">✓</span>'
            if value
            else '<span class="false_bool">✗</span>'
        )

    if isinstance(value, float):
        return f"{value:,.6g}"

    if isinstance(value, int):
        return f"{value:,}"

    return str(value)

def _dict_signature(data):
    if not isinstance(data, dict):
        return ()

    return tuple(
        (
            key,
            _dict_signature(value) if isinstance(value, dict) else None
        )
        for key, value in data.items()
    )

def _same_signature(*dicts):
    """Return True if all dictionaries have the same nested structure."""
    if len(dicts) < 2:
        return True

    signature = _dict_signature(dicts[0])
    passed = all(_dict_signature(d) == signature for d in dicts[1:])
    if not passed:
        print("Signatures do not match.")
        # for d in dicts:
        #     print(_dict_signature(d))
    return passed

def _align_dicts(*dicts):
    keys = set().union(*(d.keys() for d in dicts))

    result = [dict(d) for d in dicts]

    for key in keys:
        values = [d.get(key) for d in dicts]

        # If at least one value is a dict, recursively align them.
        dict_values = [v for v in values if isinstance(v, dict)]

        if dict_values:
            aligned = _align_dicts(*[
                v if isinstance(v, dict) else {}
                for v in values
            ])

            for d, value in zip(result, aligned):
                d[key] = value
        else:
            for d, value in zip(result, values):
                if key not in d:
                    d[key] = None

    return result

def _section_row(key, level=0, colspan=1, collapsed=False):
    return f"""    
                        <tr class="section-row level-{level}{" collapsed" if collapsed else ""}">
                            <td class="label" colspan="{colspan}">{escape(str(key))}</td>
                        </tr>"""

def _value_row(key, values=None, level=0, chart=True):
    values = values or []

    nums = []
    for v in values:
        if isinstance(v, bool):
            nums.append(None)
        else:
            try:
                numeric_value = float(v)
                nums.append(numeric_value if math.isfinite(numeric_value) else None)
            except (TypeError, ValueError, OverflowError):
                nums.append(None)

    valid = [v for v in nums if v is not None]
    total = sum(valid)
    max_abs = max((abs(v) for v in valid), default=0)
    has_negative = any(v < 0 for v in valid)
    is_proportion = not has_negative and abs(total - 1) < 0.001

    cells = []

    for original, v in zip(values, nums):
        bar = ""

        if chart and v is not None and max_abs:
            if is_proportion:
                height = v * 100
                position = "bottom: 0"
                cls = "value-bar proportion-bar"

            elif has_negative:
                height = abs(v) / max_abs * 50

                if v >= 0:
                    position = "bottom: 50%"
                    cls = "value-bar"
                else:
                    position = "top: 50%"
                    cls = "value-bar negative-bar"

            else:
                height = v / max_abs * 100
                position = "bottom: 0"
                cls = "value-bar"

            bar = (
                f'<div class="{cls}" '
                f'style="height:{height:.1f}%; {position}"></div>'
            )

        cells.append(f'''
                            <td class="value">
                                <span>{_fmt_value(key, original)}</span>
                                <div class="value-bar-container">
                                    {bar}
                                </div>
                            </td>''')

    return f"""
                        <tr class="value-row level-{level}">
                            <td class="label">{escape(str(key))}</td>
                            {"".join(cells).strip()}
                        </tr>"""

def _render_rows(dict_list, level=0, path="", collapsed_paths=None, no_chart_keys=None):
    """Flatten nested dictionaries into table rows."""
    collapsed_paths = collapsed_paths or set()
    no_chart_keys = no_chart_keys or set()
    rows = []
    for key, value in dict_list[0].items():
        current_path = f"{path}.{key}" if path else str(key)
        values = [d[key] for d in dict_list]
        display_key = DISPLAY_KEY_DICT.get(
            current_path,
            DISPLAY_KEY_DICT.get(key, key),
        )

        if isinstance(value, dict):
            collapsed = current_path in collapsed_paths
            rows.append(_section_row(display_key, level=level, colspan=len(dict_list)+1, collapsed=collapsed))
            rows.extend(_render_rows(values, level=level + 1, path=current_path, collapsed_paths=collapsed_paths, no_chart_keys=no_chart_keys))

        else:
            rows.append(_value_row(display_key, values, level=level, chart=key not in no_chart_keys))

    return rows

# column_names = [{'name': , 'link': }, ...]
def _render_header(object_type, column_names):
    cells = []
    segment_names = []

    for column in column_names:
        name = escape(str(column["name"]))
        link = column.get("link")

        if link:
            name = f'<a href="../{escape(str(link))}">{name}</a>'

        cells.append(f'''
                            <th class="value">{name}</th>''')
        segment_name = column.get("segment_name")
        if segment_name is not None:
            segment_name = str(segment_name)
            if len(segment_name) > 7:
                segment_name = f"{segment_name[:7]}…"
            segment_names.append(
                f'<th class="value segment-name">{escape(segment_name)}</th>'
            )
        else:
            segment_names.append('<th class="value segment-name"></th>')

    header = f"""<tr class="header-row">
                            <th class="label"><a href="{INDEX_HTML}/#{escape(str(object_type).lower())}s">{escape(str(object_type))}</a></th>
                            {"".join(cells).strip()}
                        </tr>"""
    if any(column.get("segment_name") is not None for column in column_names):
        header += f'''\n                        <tr class="segment-name-row">
                            <th class="label"></th>
                            {"".join(segment_names)}
                        </tr>'''
    return header

def _render_table(header, rows): 
    return f"""<thead>
                        {header}    
                    </thead>
                    <tbody>
                        {"".join(rows).strip()}    
                    </tbody>"""

def _url_exists(url):
    try:
        return requests.get(url, stream=True, timeout=2).ok
    except requests.RequestException:
        return False

def _render_images(output_file, meta_dict):
    images = []

    sa_image = Path(output_file).with_suffix(".png")
    if sa_image.exists():
        images.append(sa_image.name)

    code = meta_dict.get('code')
    if code:
        url = f"{QUARTERLY_PERFORMANCES_URL}/data/{code}.png"
        if _url_exists(url):
            images.append(url)
        else: 
            print(f"Could not reach URL: {url}")

    # ------------------------------
    # may add additional images here
    # ------------------------------

    return "".join(
        f'''
            <div class="chart-card">
                <img src="{image}" class="analysis-image" onclick="openPopup('{image}');">
            </div>'''
        for image in images
    ).strip()

def _get_ext_links(code):
    if isinstance(code, str): 
        return f'''
                    <div class="ext-links">
                        <a class="ext-link" href="{INDEX_HTML}">QP</a>
                        <a class="ext-link" href="#" onclick="openPopup('{get_NAVER_url(code)}', true); return false;">NV</a>
                        <a class="ext-link" href="#" onclick="openPopup('{get_FN_GUIDE_url(code)}', true); return false;">FN</a>
                    </div>'''
    return f'''
                    <div class="ext-links">
                        <a class="ext-link" href="{INDEX_HTML}">QP</a>
                    </div>'''

def _render_financials(target_type, target_key, financials_names: list, financials_list: list, output_file: Path, collapsed_paths=None, no_chart_keys=None):
    meta_dict = financials_list[0].get('meta', {})
    header = _render_header(target_type, financials_names)
    rows = _render_rows(financials_list, collapsed_paths=collapsed_paths, no_chart_keys=no_chart_keys)
    table_content = _render_table(header, rows)
    images = _render_images(output_file, meta_dict)
    ext_links = _get_ext_links(meta_dict.get('code'))

    return f"""<h3 class="financials-heading">
        <span>Financials Analysis</span>
        <span class="model-instance-actions">
            <button class="model-instance-delete-button" type="button"
                data-object-type="{escape(str(target_type), quote=True)}"
                data-object-id="{escape(str(target_key), quote=True)}">Delete</button>
            <button class="model-instance-update-button" type="button"
                data-object-type="{escape(str(target_type), quote=True)}"
                data-object-id="{escape(str(target_key), quote=True)}">Update</button>
        </span>
    </h3>
    <div class="dashboard">
        <div class="table-panel">
            <div class="table-wrapper">
                <div class="table-controls">
                    <button onclick="expandAll()">+</button>
                    <button onclick="collapseAll()">-</button>
                    {ext_links}
                </div>
                <table class="dict-table">
                    {table_content}
                </table>
            </div>
        </div>
        <div class="charts-panel">
            {images}
        </div>
    </div>"""

def _render_qualitative_value(value):
    """Recursively render dict, list, and scalar values as HTML."""
    # Pydantic BaseModel → dict
    if isinstance(value, BaseModel):
        value = value.model_dump()

    # Nested dict
    if isinstance(value, dict):
        rows = []

        for key, val in value.items():
            rows.append(f"""
                            <tr>
                                <th>{escape(str(key))}</th>
                                <td>{_render_qualitative_value(val)}</td>
                            </tr>""")

        return f"""<table class="qualitative-table">
                        <tbody>
                            {"".join(rows).strip()}
                        </tbody>
                    </table>"""

    # List
    elif isinstance(value, list):
        rows = []

        for item in value:
            rows.append(f"""
                            <tr>
                                <td>{_render_qualitative_value(item)}</td>
                            </tr>""")

        return f"""<table class="qualitative-table">
                        <tbody>
                            {"".join(rows).strip()}
                        </tbody>
                    </table>"""

    # Simple value
    else:
        return escape(str(value))

def _render_info_section(section):
    """
    Render an InfoSection.

    The actual values are also embedded as data attributes so
    JavaScript can populate the edit controls.
    """

    data = section.model_dump()

    rows = []

    for field_name, value in data.items():

        # reviewed gets special visual treatment
        if field_name == "reviewed":
            status = "Reviewed" if value else "Not reviewed"
            cls = "reviewed" if value else "not-reviewed"

            rows.append(f"""
                            <tr class="reviewed-row">
                                <th>reviewed</th>
                                <td>
                                    <span class="reviewed-status {cls}">
                                        {status}
                                    </span>
                                </td>
                            </tr>
            """)
            continue

        if isinstance(value, bool):
            checked = " checked" if value else ""
            rows.append(f"""
                            <tr>
                                <th>{escape(str(field_name))}</th>
                                <td>
                                    <input
                                        class="qualitative-checkbox"
                                        type="checkbox"
                                        aria-label="{escape(str(field_name))}"
                                        disabled{checked}
                                    >
                                </td>
                            </tr>
            """)
            continue

        rows.append(f"""
                            <tr>
                                <th>{escape(str(field_name))}</th>
                                <td>{_render_qualitative_value(value)}</td>
                            </tr>
        """)

    return f"""
                <div class="info-section-view">
                    <table class="qualitative-table">
                        <tbody>
                            {"".join(rows).strip()}
                        </tbody>
                    </table>
                </div>
    """

def _render_info_card(section_name, section, target_type, target_key):

    reviewed = section.reviewed

    if reviewed:
        status_html = """
                    <span class="reviewed-badge reviewed">
                        ✓ Reviewed
                    </span>
        """
    else:
        status_html = """
                    <span class="reviewed-badge not-reviewed">
                        ○ Not reviewed
                    </span>
        """

    content = _render_info_section(section)

    return f"""
                <div
                    class="qualitative-card"
                    data-section="info_section"
                    data-object-type="{escape(str(target_type))}"
                    data-object-id="{escape(str(target_key))}"
                >

                    <div class="qualitative-header">

                        <h4>{escape(str(section_name))}</h4>

                        <div class="qualitative-actions">

                            {status_html}

                            <input
                                class="edit-password"
                                type="password"
                                maxlength="4"
                                inputmode="numeric"
                                placeholder="....(p)"
                            >

                            <button
                                class="edit-button"
                                type="button"
                                title="Edit"
                            >✎</button>

                        </div>
                    </div>

                    <div class="qualitative-content">
                        {content}
                    </div>

                </div>
    """

def _render_qualitative(qual_dict, target_type, target_key, info_section_validator):
    if not qual_dict:
        return ""

    cards = []

    for key, value in qual_dict.items():

        title = escape(str(key))

        if isinstance(value, info_section_validator):

            cards.append(
                _render_info_card(
                    key,
                    value,
                    target_type,
                    target_key
                )
            )

        else:

            content = _render_qualitative_value(value)
            actions = ""
            if key == "news":
                actions = f"""
                    <div class="qualitative-actions">
                        <button class="news-update-button" type="button"
                            data-object-type="{escape(str(target_type), quote=True)}"
                            data-object-id="{escape(str(target_key), quote=True)}">Update</button>
                    </div>
                """

            cards.append(f"""
                <div class="qualitative-card"{" data-news-card" if key == "news" else ""}>

                    <div class="qualitative-header">
                        <h4>{title}</h4>
                        {actions}
                    </div>

                    <div class="qualitative-content">
                        {content}
                    </div>

                </div>
            """)

    return f"""
        <h3>Qualitative Analysis</h3>

        <div class="qualitative-section">
            <div class="qualitative-grid">
                {"".join(cards).strip()}
            </div>
        </div>
    """

def _render_llm_research(
    research: str,
    target_key: str,
    show_delete: bool = False,
    updated: str = "",
    *,
    target_type: str,
    extra_action: str = "",
):
    research = (research or "").strip()
    if not research and not show_delete and not extra_action:
        return ""

    dialog_id = "llm-research-dialog-" + "".join(
        char if char.isalnum() or char in "-_" else "-"
        for char in str(target_key)
    )
    research_hash_attr = ""
    content = '<p class="llm-research-missing">LLM research md file is missing...</p>'
    delete_button = ""
    research_button_class = "llm-research-link"
    if not research:
        research_button_class += " llm-research-missing"
    updated_label = (
        f'<p class="llm-research-updated">Updated: {escape(updated)}</p>'
        if research and updated else ""
    )
    if research:
        research_hash = hashlib.sha256(research.encode("utf-8")).hexdigest()
        content = MarkdownIt().enable("table").render(research)
        research_hash_attr = f' data-research-hash="{research_hash}"'
        delete_button = '<button class="llm-research-delete-button" type="button">Delete</button>'
    return f"""
    <div class="llm-research-trigger-row" data-object-type="{escape(target_type, quote=True)}"
        data-object-id="{escape(str(target_key), quote=True)}">
        <button class="{research_button_class}" type="button" aria-haspopup="dialog"
            aria-controls="{escape(dialog_id, quote=True)}">LLM Research (l)</button>
        {extra_action}
    </div>
    <dialog class="llm-research-dialog" id="{escape(dialog_id, quote=True)}"
        data-object-type="{escape(target_type, quote=True)}" data-object-id="{escape(str(target_key), quote=True)}"{research_hash_attr}
        aria-labelledby="{escape(dialog_id, quote=True)}-title">
        <div class="llm-research-dialog-header">
            <h2 id="{escape(dialog_id, quote=True)}-title">LLM Research</h2>
            <div class="llm-research-dialog-header-actions">
                {delete_button}
                <button class="llm-research-close" type="button" aria-label="Close research">×</button>
            </div>
        </div>
        <div class="llm-research-dialog-content">
            {updated_label}
            <div class="llm-research-markdown">{content}</div>
            <div class="llm-research-dialog-actions">
                <span class="llm-research-status" role="status" aria-live="polite"></span>
            </div>
        </div>
    </dialog>
    """


def _render_roma_plot(codes, target_key: str):
    """Render a ROMA plot button and its serialized Plotly figure."""
    plot_items = list(codes or [])
    if not plot_items:
        return ""

    plot_id = "roma-plot-" + "".join(
        char if char.isalnum() or char in "-_" else "-"
        for char in str(target_key)
    )
    try:
        from build.analysis.roma_plot import draw_roma
        figure_html = draw_roma(plot_items).to_html(
            full_html=False,
            include_plotlyjs="cdn",
            config={"responsive": True},
        )
    except Exception as exc:
        figure_html = f'<p class="roma-plot-error">Could not create ROMA plot: {escape(str(exc))}</p>'

    return f'''
        <button class="roma-plot-link" type="button" aria-haspopup="dialog"
            aria-controls="{escape(plot_id, quote=True)}" title="ROMA plot (r)">ROMA plot (r)</button>
        <template class="roma-plot-template" id="{escape(plot_id, quote=True)}"
            data-title="ROMA plot — {escape(str(target_key), quote=True)}">{figure_html}</template>
    '''


# list all news articles in the given folder newest first
def _render_news(news_dir: Path, target_type: str, target_key: str):
    if not news_dir.exists():
        return ""

    paths = sorted(
        news_dir.glob("*.md"),
        key=lambda p: p.name,
        reverse=True,
    )

    if not paths:
        return ""

    rows = []

    for path in paths:
        # URL path served by Node, NOT file://
        relative_path = path.relative_to(BASE_DATA_DIR).as_posix()
        url = "/" + relative_path

        rows.append(f"""
            <div class="news-row" data-news-file="{escape(path.name, quote=True)}"
                data-news-path="{escape(relative_path, quote=True)}"
                data-object-type="{escape(str(target_type), quote=True)}"
                data-object-id="{escape(str(target_key), quote=True)}">
                <a href="#" onclick="openPopup('{url}'); return false;">
                    {escape(path.stem.replace('_', ' '))}
                </a>
                <button class="news-delete-button" type="button" title="Delete article"
                    aria-label="Delete article">×</button>
            </div>
        """)

    return f"""
    <h3>News</h3>
    <div class="news-section">
        {"".join(rows).strip()}
    </div>
    """

def render_html(target_class, 
                target_key, 
                financials_names: list, 
                financials_dicts: list, 
                qual_dict: dict, 
                news_dir: Path,
                output_file: Path, 
                template_html:Path=TEMPLATE_HTML, 
                collapsed_paths=COLLAPSED_PATHS, 
                no_chart_keys=NO_CHART_KEYS,
                info_section_validator=None,
                llm_research: str = "",
                llm_research_updated: str = "",
                show_research_delete: bool = False,
                roma_codes=None):

    if not financials_dicts:
        raise ValueError("dict_list cannot be empty")

    if len(financials_names) != len(financials_dicts):
        print(financials_names)
        print(financials_dicts)
        raise ValueError("column_names and dict_list must have the same length")

    if not _same_signature(*financials_dicts):
        print("Aligning financial data...")
        financials_dicts = _align_dicts(*financials_dicts)

    page_name = f"[{escape(str(target_class).lower())}] {escape(str(financials_names[0]['name']))}"
    financials_section = _render_financials(target_class, target_key, financials_names, financials_dicts, output_file, collapsed_paths, no_chart_keys)
    qual_section = _render_qualitative(qual_dict, target_class, target_key, info_section_validator)
    roma_markup = _render_roma_plot(roma_codes, target_key)
    mp_markup = ""
    if target_class in {"Component", "ValueChain"}:
        mp_markup = f'''
        <button class="mp-plot-link" type="button" aria-haspopup="dialog"
            data-object-type="{escape(str(target_class), quote=True)}"
            data-object-id="{escape(str(target_key), quote=True)}"
            title="Margin vs PER plot (m)">MP plot (m)</button>
        '''
    news_section = _render_llm_research(
        llm_research,
        target_key,
        show_delete=show_research_delete,
        updated=llm_research_updated,
        target_type=target_class,
        extra_action=roma_markup + mp_markup,
    ) + _render_news(news_dir, target_class, target_key)

    html = template_html.read_text(encoding="utf-8")
    html = html.replace("{{ page_name }}", page_name)
    html = html.replace("{{ year }}", year)
    html = html.replace("{{ financials }}", financials_section)
    html = html.replace("{{ qualitative }}", qual_section)
    html = html.replace("{{ news }}", news_section)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(html, encoding="utf-8")
    print(f"Wrote file: {output_file}")
