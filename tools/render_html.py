import requests
from html import escape
from datetime import datetime
from build.tools.settings import THIS_PROJECT, QUARTERLY_PERFORMANCES_URL, INDEX_HTML, BASE_DATA_DIR, get_FN_GUIDE_url, get_NAVER_url
from pydantic import BaseModel
from pathlib import Path

# -----------------------------------------------------------------------------------
# Display dict in html
# -----------------------------------------------------------------------------------
TEMPLATE_HTML = Path(THIS_PROJECT) / "analysis" / "templates"  / "dict_template.html"

COLLAPSED_PATHS = {
    'meta', 
    'assess_data.alpha_beta.from_start_date', 
    'shape.financials'
}
NO_CHART_KEYS = {
    'key',
    'unit',
    'code',
    '-m_rank', 
    '-r_rank',
    '-o_rank',
}
year = str(datetime.today().year)

def _fmt_value(key, value):
    if value is None:
        return "-"

    if isinstance(value, bool):
        return (
            '<span class="true_bool">✓</span>'
            if value
            else '<span class="false_bool">✗</span>'
        )

    if isinstance(value, float):
        if "(pct)" in key.lower() or "(%)" in key.lower():
            return f"{value:.2%}"
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
        print(f"Signature mismatching: ")
        for d in dicts:
            print(_dict_signature(d))
    return passed

def _section_row(key, level=0, colspan=1, collapsed=False):
    return f"""    
                        <tr class="section-row level-{level}{" collapsed" if collapsed else ""}">
                            <td class="label" colspan="{colspan}">{escape(str(key))}</td>
                        </tr>"""

# simpler core func 
# def _value_row(key, values=None, level=0):
#     values = values or []
#     cells = "".join(
#         f'''
#                             <td class="value">{_fmt_value(key, v)}</td>'''
#         for v in values
#     ).strip()

#     return f"""        
#                         <tr class="value-row level-{level}">
#                             <td class="label">{escape(str(key))}</td>
#                             {cells}
#                         </tr>"""
def _value_row(key, values=None, level=0, chart=True):
    values = values or []

    nums = []
    for v in values:
        if isinstance(v, bool):
            nums.append(None)
        else:
            try:
                nums.append(float(v))
            except (TypeError, ValueError):
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

        if isinstance(value, dict):
            collapsed = current_path in collapsed_paths
            rows.append(_section_row(key, level=level, colspan=len(dict_list)+1, collapsed=collapsed))
            rows.extend(_render_rows(values, level=level + 1, path=current_path, collapsed_paths=collapsed_paths, no_chart_keys=no_chart_keys))

        else:
            rows.append(_value_row(key, values, level=level, chart=key not in no_chart_keys))

    return rows

# column_names = [{'name': , 'link': }, ...]
def _render_header(object_type, column_names):
    cells = []

    for column in column_names:
        name = escape(str(column["name"]))
        link = column.get("link")

        if link:
            name = f'<a href="../{escape(str(link))}">{name}</a>'

        cells.append(f'''
                            <th class="value">{name}</th>''')

    return f"""<tr class="header-row">
                            <th class="label"><a href="{INDEX_HTML}/#{escape(str(object_type).lower())}s">{escape(str(object_type))}</a></th>
                            {"".join(cells).strip()}
                        </tr>"""

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
            print(f'url {url} not reached')

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

def _render_financials(target_type, target_key, financials_names: list, financials_list: list, output_file: Path, collapsed_paths=COLLAPSED_PATHS, no_chart_keys=NO_CHART_KEYS):
    meta_dict = financials_list[0].get('meta', {})
    header = _render_header(target_type, financials_names)
    rows = _render_rows(financials_list, collapsed_paths=collapsed_paths, no_chart_keys=no_chart_keys)
    table_content = _render_table(header, rows)
    images = _render_images(output_file, meta_dict)
    ext_links = _get_ext_links(meta_dict.get('code'))

    return f"""<h3 class="financials-heading">
        <span>Financials Analysis</span>
        <button class="model-instance-update-button" type="button"
            data-object-type="{escape(str(target_type), quote=True)}"
            data-object-id="{escape(str(target_key), quote=True)}">↻ Update</button>
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
                                placeholder="••••"
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

            cards.append(f"""
                <div class="qualitative-card">

                    <div class="qualitative-header">
                        <h4>{title}</h4>
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

# list all news articles in the given folder newest first
def _render_news(news_dir):
    if news_dir is None or not news_dir.exists():
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
        url = "/" + path.relative_to(BASE_DATA_DIR).as_posix()

        rows.append(f"""
            <div class="news-row">
                <a href="#" onclick="openPopup('{url}'); return false;">
                    {path.stem.replace('_', ' ')}
                </a>
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
                news_dir: None,
                output_file: Path, 
                template_html:Path=TEMPLATE_HTML, 
                collapsed_paths=COLLAPSED_PATHS, 
                info_section_validator=None):

    if not financials_dicts:
        raise ValueError("dict_list cannot be empty")

    if len(financials_names) != len(financials_dicts):
        raise ValueError("column_names and dict_list must have the same length")

    if not _same_signature(*financials_dicts):
        raise ValueError("signatures not matching")

    page_name = f"[{escape(str(target_class).lower())}] {escape(str(financials_names[0]['name']))}"
    financials_section = _render_financials(target_class, target_key, financials_names, financials_dicts, output_file, collapsed_paths)
    qual_section = _render_qualitative(qual_dict, target_class, target_key, info_section_validator)
    news_section = _render_news(news_dir)

    html = template_html.read_text(encoding="utf-8")
    html = html.replace("{{ page_name }}", page_name)
    html = html.replace("{{ year }}", year)
    html = html.replace("{{ financials }}", financials_section)
    html = html.replace("{{ qualitative }}", qual_section)
    html = html.replace("{{ news }}", news_section)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(html, encoding="utf-8")
    print(f"File {output_file} is written...")
