from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

from .schemas import FinalReportContent, FinalReportItem

RED = RGBColor(0xFF, 0x00, 0x00)
GRAY = RGBColor(0x80, 0x80, 0x80)
BLACK = RGBColor(0x00, 0x00, 0x00)


def _add_run(paragraph, text: str, *, bold: bool = False, color: RGBColor | None = None) -> None:
    run = paragraph.add_run(text)
    run.bold = bold
    run.font.size = Pt(10.5)
    if color is not None:
        run.font.color.rgb = color


def _detect_highlight_phrases(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    fixed_phrases = [
        "征求意见稿",
        "正式实施",
        "修订草案",
        "专项行动",
        "平安集团不直接适用",
    ]
    for phrase in fixed_phrases:
        for m in re.finditer(re.escape(phrase), text):
            spans.append((m.start(), m.end()))

    patterns = [
        r"对平安[^。；，]{2,40}有直接影响",
        r"后续将改变[^。；]{2,40}",
        r"(?:应立即|应尽快|应优先|应开展|应修订|应调整|应切换|可关注|可评估)[^。；]{0,36}",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text):
            spans.append((m.start(), m.end()))

    spans.sort()
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged[:4]


def _append_paragraph_with_highlight(doc: Document, text: str) -> None:
    if not text:
        return
    paragraph = doc.add_paragraph(style="Normal")
    paragraph.paragraph_format.space_after = Pt(6)
    paragraph.paragraph_format.line_spacing = 1.35
    spans = _detect_highlight_phrases(text)
    if not spans:
        _add_run(paragraph, text, color=BLACK)
        return

    cursor = 0
    for start, end in spans:
        if start > cursor:
            _add_run(paragraph, text[cursor:start], color=BLACK)
        _add_run(paragraph, text[start:end], color=RED)
        cursor = end
    if cursor < len(text):
        _add_run(paragraph, text[cursor:], color=BLACK)


def _render_item(doc: Document, item: FinalReportItem, index: int) -> None:
    title_para = doc.add_paragraph(style="Normal")
    title_para.paragraph_format.space_before = Pt(10)
    _add_run(title_para, f"{index}. {item.title}", bold=True, color=BLACK)

    _append_paragraph_with_highlight(doc, item.paragraph1)
    _append_paragraph_with_highlight(doc, item.paragraph2)


def render_docx(report: FinalReportContent, output_path: Path) -> Path:
    doc = Document()
    title = doc.add_heading(report.report_title, level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in title.runs:
        run.font.color.rgb = BLACK

    date_para = doc.add_paragraph(report.report_date)
    date_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    date_para.paragraph_format.space_after = Pt(12)

    for idx, item in enumerate(report.items, start=1):
        _render_item(doc, item, idx)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    return output_path
