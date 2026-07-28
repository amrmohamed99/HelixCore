"""
Report builder — generates PDF and HTML reports from screening results.
Uses reportlab for PDF and Jinja2 for HTML templating.
"""

import os
import json
import time
from html import escape
from typing import Any

from backend.config import APP_VERSION

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, Image as RLImage,
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

try:
    from jinja2 import Environment, select_autoescape
    JINJA2_AVAILABLE = True
except ImportError:
    JINJA2_AVAILABLE = False


# ──── Color palette (dark theme) ────
_ACCENT      = "#7B73FF"
_ACCENT_DIM  = "#5A52D5"
_GREEN       = "#34D399"
_AMBER       = "#FBBF24"
_ROSE        = "#FB7185"
_BG_PAGE     = "#0F1019"
_BG_CARD     = "#181A27"
_BG_ROW_A    = "#1C1E2E"
_BG_ROW_B    = "#20223A"
_BORDER      = "#2D2F48"
_TEXT_PRI    = "#ECEAF6"
_TEXT_SEC    = "#9896B0"
_TEXT_MUTED  = "#6E6C88"


def _safe_text(value: Any) -> str:
    """Escape user/result content before ReportLab parses paragraph markup."""
    return escape(str(value), quote=True)


def _dark_page_bg(canvas, doc):
    """Draw a full-page dark background on every page."""
    canvas.saveState()
    canvas.setFillColor(HexColor(_BG_PAGE))
    canvas.rect(0, 0, doc.pagesize[0], doc.pagesize[1], fill=1, stroke=0)
    # Subtle accent line at top
    canvas.setFillColor(HexColor(_ACCENT))
    canvas.rect(0, doc.pagesize[1] - 3, doc.pagesize[0], 3, fill=1, stroke=0)
    # Footer
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(HexColor(_TEXT_MUTED))
    canvas.drawCentredString(
        doc.pagesize[0] / 2, 12 * mm,
        f"Helix Core v{APP_VERSION} — AI-Powered Drug Discovery Suite  |  Page {canvas.getPageNumber()}"
    )
    canvas.restoreState()


def _build_styles():
    """Create reportlab paragraph styles matching Helix Core dark theme."""
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        "CoverTitle", parent=styles["Heading1"],
        fontSize=26, textColor=HexColor(_ACCENT), spaceAfter=6,
        fontName="Helvetica-Bold",
    ))
    styles.add(ParagraphStyle(
        "CoverMeta", parent=styles["Normal"],
        fontSize=10, textColor=HexColor(_TEXT_SEC), leading=15, spaceAfter=2,
    ))
    styles.add(ParagraphStyle(
        "HeadingCustom", parent=styles["Heading1"],
        fontSize=16, textColor=HexColor(_ACCENT), spaceAfter=10,
        fontName="Helvetica-Bold",
    ))
    styles.add(ParagraphStyle(
        "SubHeadingCustom", parent=styles["Heading2"],
        fontSize=12, textColor=HexColor(_TEXT_PRI), spaceAfter=6,
        fontName="Helvetica-Bold",
    ))
    styles.add(ParagraphStyle(
        "BodyCustom", parent=styles["Normal"],
        fontSize=9, textColor=HexColor(_TEXT_SEC), leading=13,
    ))
    styles.add(ParagraphStyle(
        "TableHeader", parent=styles["Normal"],
        fontSize=8.5, textColor=HexColor("#FFFFFF"), fontName="Helvetica-Bold",
    ))
    styles.add(ParagraphStyle(
        "TableCell", parent=styles["Normal"],
        fontSize=8.5, textColor=HexColor(_TEXT_PRI), leading=11,
    ))
    styles.add(ParagraphStyle(
        "StatLabel", parent=styles["Normal"],
        fontSize=9, textColor=HexColor(_TEXT_SEC),
    ))
    styles.add(ParagraphStyle(
        "StatValue", parent=styles["Normal"],
        fontSize=9, textColor=HexColor(_TEXT_PRI),
    ))
    return styles


def generate_pdf_report(
    output_path: str,
    title: str = "Helix Core Report",
    sections: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Generate a professional PDF report.

    Each section dict should have:
        - title: str
        - type: 'table' | 'text' | 'stats' | 'chart_placeholder'
        - data: varies by type
            - table: { headers: [...], rows: [[...], ...] }
            - text: str
            - stats: { label: value, ... }
    """
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("reportlab not installed — cannot generate PDF")

    sections = sections or []
    metadata = metadata or {}
    styles = _build_styles()

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=25 * mm, bottomMargin=20 * mm,
    )

    story: list = []

    # ── Cover page ──
    story.append(Spacer(1, 55 * mm))

    # Accent bar decoration
    cover_bar = Table([[""]], colWidths=[40 * mm], rowHeights=[4])
    cover_bar.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), HexColor(_ACCENT)),
        ('LINEBELOW', (0, 0), (-1, -1), 0, HexColor(_ACCENT)),
    ]))
    story.append(cover_bar)
    story.append(Spacer(1, 5 * mm))

    story.append(Paragraph(_safe_text(title), styles["CoverTitle"]))
    story.append(Spacer(1, 6 * mm))

    # Metadata block
    meta_lines = [f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}"]
    if metadata.get("project"):
        meta_lines.append(f"Project: {_safe_text(metadata['project'])}")
    if metadata.get("author"):
        meta_lines.append(f"Author: {_safe_text(metadata['author'])}")
    meta_lines.append(f"Helix Core v{APP_VERSION} — AI-Powered Drug Discovery Suite")
    for line in meta_lines:
        story.append(Paragraph(line, styles["CoverMeta"]))

    story.append(PageBreak())

    # ── Sections ──
    for section in sections:
        sec_title = section.get("title", "Section")
        sec_type = section.get("type", "text")
        sec_data = section.get("data", "")

        story.append(Paragraph(_safe_text(sec_title), styles["HeadingCustom"]))
        story.append(Spacer(1, 2 * mm))

        if sec_type == "text":
            story.append(Paragraph(_safe_text(sec_data), styles["BodyCustom"]))

        elif sec_type == "stats":
            if isinstance(sec_data, dict):
                stat_items = [
                    [Paragraph(_safe_text(k), styles["StatLabel"]),
                     Paragraph(_safe_text(v), styles["StatValue"])]
                    for k, v in sec_data.items()
                ]
                if stat_items:
                    tbl = Table(stat_items, colWidths=[80 * mm, 80 * mm])
                    tbl.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, -1), HexColor(_BG_CARD)),
                        ('GRID', (0, 0), (-1, -1), 0.5, HexColor(_BORDER)),
                        ('BACKGROUND', (0, 0), (0, -1), HexColor(_BG_ROW_B)),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('LEFTPADDING', (0, 0), (-1, -1), 8),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                        ('TOPPADDING', (0, 0), (-1, -1), 6),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                        ('ROUNDEDCORNERS', [4, 4, 4, 4]),
                    ]))
                    story.append(tbl)

        elif sec_type == "table":
            headers = sec_data.get("headers", [])
            rows = sec_data.get("rows", [])
            if headers and rows:
                header_row = [Paragraph(_safe_text(h), styles["TableHeader"]) for h in headers]
                data_rows = [
                    [Paragraph(_safe_text(cell), styles["TableCell"]) for cell in row]
                    for row in rows[:50]
                ]
                all_rows = [header_row] + data_rows
                n_cols = len(headers)
                col_w = (170 * mm) / max(n_cols, 1)
                tbl = Table(all_rows, colWidths=[col_w] * n_cols)
                tbl.setStyle(TableStyle([
                    # Header row
                    ('BACKGROUND', (0, 0), (-1, 0), HexColor(_ACCENT)),
                    ('TEXTCOLOR', (0, 0), (-1, 0), HexColor("#FFFFFF")),
                    # Alternating row backgrounds
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor(_BG_ROW_A), HexColor(_BG_ROW_B)]),
                    # Grid & borders
                    ('GRID', (0, 0), (-1, -1), 0.5, HexColor(_BORDER)),
                    ('LINEBELOW', (0, 0), (-1, 0), 1.5, HexColor(_ACCENT_DIM)),
                    # Padding
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 6),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                    ('TOPPADDING', (0, 0), (-1, -1), 5),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ]))
                story.append(tbl)
                if len(rows) > 50:
                    story.append(Spacer(1, 2 * mm))
                    story.append(Paragraph(
                        f"… {len(rows) - 50} more rows omitted", styles["BodyCustom"]
                    ))

        story.append(Spacer(1, 8 * mm))

    doc.build(story, onFirstPage=_dark_page_bg, onLaterPages=_dark_page_bg)
    return output_path


# ──── HTML Report ────

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ title }}</title>
<style>
  :root {
    --bg: #1A1B2E; --bg-card: #1E1F33; --border: #2E2D45;
    --text: #E8E6F0; --text-sec: #8B89A0; --accent: #6C63FF;
    --green: #22C55E; --amber: #F59E0B; --rose: #EF4444;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: var(--bg); color: var(--text); font-family: 'Segoe UI', system-ui, sans-serif; padding: 40px; }
  .header { text-align: center; margin-bottom: 40px; }
  .header h1 { color: var(--accent); font-size: 2rem; margin-bottom: 8px; }
  .header p { color: var(--text-sec); font-size: 0.85rem; }
  .section { background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; padding: 24px; margin-bottom: 24px; }
  .section h2 { color: var(--accent); font-size: 1.15rem; margin-bottom: 14px; border-bottom: 1px solid var(--border); padding-bottom: 8px; }
  .stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }
  .stat-card { background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 14px; text-align: center; }
  .stat-card .value { font-size: 1.6rem; font-weight: 700; color: var(--accent); }
  .stat-card .label { font-size: 0.75rem; color: var(--text-sec); margin-top: 4px; }
  table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
  th { background: var(--accent); color: #fff; padding: 8px 10px; text-align: left; }
  td { padding: 6px 10px; border-bottom: 1px solid var(--border); }
  tr:nth-child(even) { background: rgba(108,99,255,0.04); }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.72rem; font-weight: 600; }
  .badge-green { background: rgba(34,197,94,0.15); color: var(--green); }
  .badge-rose { background: rgba(239,68,68,0.15); color: var(--rose); }
  .badge-amber { background: rgba(245,158,11,0.15); color: var(--amber); }
  .text-block { color: var(--text-sec); line-height: 1.6; font-size: 0.88rem; }
  .footer { text-align: center; padding: 30px; color: var(--text-sec); font-size: 0.75rem; }
  @media print { body { background: #fff; color: #333; } .section { border-color: #ddd; background: #fafafa; } th { background: #6C63FF; } }
</style>
</head>
<body>
<div class="header">
  <h1>🧬 {{ title }}</h1>
  <p>Generated: {{ generated_at }} | Helix Core v{{ app_version }}</p>
  {% if project %}<p>Project: {{ project }}</p>{% endif %}
</div>

{% for section in sections %}
<div class="section">
  <h2>{{ section.title }}</h2>

  {% if section.type == 'text' %}
    <div class="text-block">{{ section.data }}</div>

  {% elif section.type == 'stats' %}
    <div class="stats-grid">
      {% for key, value in section.data.items() %}
      <div class="stat-card">
        <div class="value">{{ value }}</div>
        <div class="label">{{ key }}</div>
      </div>
      {% endfor %}
    </div>

  {% elif section.type == 'table' %}
    <table>
      <thead><tr>
        {% for h in section.data.headers %}<th>{{ h }}</th>{% endfor %}
      </tr></thead>
      <tbody>
        {% for row in section.data.rows %}
        <tr>
          {% for cell in row %}<td>{{ cell }}</td>{% endfor %}
        </tr>
        {% endfor %}
      </tbody>
    </table>
  {% endif %}
</div>
{% endfor %}

<div class="footer">
  Helix Core — AI-Powered Drug Discovery Suite &copy; {{ year }}
</div>
</body>
</html>
"""


def generate_html_report(
    output_path: str,
    title: str = "Helix Core Report",
    sections: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Generate a standalone HTML report."""
    if not JINJA2_AVAILABLE:
        raise RuntimeError("jinja2 not installed — cannot generate HTML report")

    sections = sections or []
    metadata = metadata or {}
    environment = Environment(
        autoescape=select_autoescape(default_for_string=True, default=True),
    )
    template = environment.from_string(_HTML_TEMPLATE)

    html = template.render(
        title=title,
        sections=sections,
        generated_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        project=metadata.get("project", ""),
        app_version=APP_VERSION,
        year=time.strftime("%Y"),
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return output_path
