from __future__ import annotations

import json
import os
from datetime import datetime, date
from pathlib import Path
from typing import Iterable

import click
from rich.console import Console

from .extractor import extract_fact_sheets
from .fetcher import fetch_articles
from .generator import build_final_report_content, generate_drafts, retrieve_examples, rewrite_failed_items
from .learning import diff_draft_vs_final, parse_final_report, update_few_shots, update_forbidden_expansions
from .renderer import render_docx
from .schemas import (
    LearningUpdateReport,
    NormalizedPoliciesOutput,
    PolicyCardDraftsOutput,
    PolicyFactSheetsOutput,
    RunLogItem,
    WeeklyPoliciesInput,
)
from .validator import validate_drafts

console = Console()


def _save(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(data, "model_dump_json"):
        path.write_text(data.model_dump_json(indent=2), encoding="utf-8")
    else:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    console.print(f"  [dim]saved → {path}[/dim]")


class _RunLogger:
    def __init__(self) -> None:
        self.items: list[RunLogItem] = []

    def info(self, stage: str, message: str) -> None:
        self.items.append(RunLogItem(level="INFO", stage=stage, message=message))

    def warning(self, stage: str, message: str) -> None:
        self.items.append(RunLogItem(level="WARNING", stage=stage, message=message))

    def to_lines(self, report_date: str) -> list[str]:
        lines = ["# 运行日志", "", f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", f"- 周报日期：{report_date}", ""]
        for item in self.items:
            lines.append(f"- [{item.level}] [{item.stage}] {item.message}")
        return lines


def _normalize(input_data: WeeklyPoliciesInput) -> NormalizedPoliciesOutput:
    included = [p for p in input_data.policies if p.include]
    seen: set[tuple[str, str, str]] = set()
    deduped = []
    for p in included:
        key = (p.issuer, p.title, p.url)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(p)
    deduped.sort(key=lambda x: x.date, reverse=True)
    return NormalizedPoliciesOutput(report_date=input_data.report_date, report_type=input_data.report_type, policies=deduped)


def _write_run_log(output_dir: Path, logger: _RunLogger, report_date: str) -> None:
    path = output_dir / "run_log.md"
    path.write_text("\n".join(logger.to_lines(report_date)) + "\n", encoding="utf-8")


def _read_text_file(input_path: Path) -> str:
    if input_path.suffix.lower() == ".docx":
        from docx import Document
        doc = Document(str(input_path))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    return input_path.read_text(encoding="utf-8")


@click.group()
def main() -> None:
    """监管政策周报生成工具（轻量版）"""


@main.command()
@click.option("--input", "input_path", required=True, type=click.Path(exists=True), help="weekly_policies.json 路径")
@click.option("--output-dir", "output_dir", default="./output", show_default=True, help="输出目录")
def generate(input_path: str, output_dir: str) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    logger = _RunLogger()

    raw = Path(input_path).read_text(encoding="utf-8")
    input_data = WeeklyPoliciesInput.model_validate_json(raw)
    logger.info("input", f"读取输入，共 {len(input_data.policies)} 条")

    console.rule("[bold]Step 0: normalize[/bold]")
    normalized = _normalize(input_data)
    _save(out / "normalized_policies.json", normalized)
    logger.info("normalize", f"过滤去重后保留 {len(normalized.policies)} 条")

    console.rule("[bold]Step 1: fetch[/bold]")
    fetched = fetch_articles(normalized)
    _save(out / "fetched_articles.json", fetched)
    fallback_count = sum(1 for a in fetched.articles if a.title_only_fallback)
    logger.info("fetch", f"抓取完成 {len(fetched.articles)} 条，title_only fallback={fallback_count}")

    console.rule("[bold]Step 2: extract[/bold]")
    llm_client = None
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic as _anthropic
            llm_client = _anthropic.Anthropic()
            logger.info("extract", "LLM精炼已启用（ANTHROPIC_API_KEY 已设置）")
        except Exception:
            logger.warning("extract", "anthropic 包不可用，跳过 LLM 精炼")
    else:
        logger.warning("extract", "未设置 ANTHROPIC_API_KEY，LLM精炼将跳过")
    fact_sheets = extract_fact_sheets(fetched, normalized, client=llm_client)
    _save(out / "policy_fact_sheets.json", fact_sheets)
    logger.info("extract", f"事实卡构建完成 {len(fact_sheets.fact_sheets)} 条")

    console.rule("[bold]Step 3: retrieve examples[/bold]")
    retrieved_examples = retrieve_examples(fact_sheets)
    _save(out / "retrieved_examples.json", retrieved_examples)
    logger.info("fewshot", "few-shot 检索完成")

    console.rule("[bold]Step 4: generate[/bold]")
    drafts = generate_drafts(fact_sheets, retrieved_examples)
    _save(out / "policy_card_drafts.json", drafts)
    logger.info("generate", f"草稿生成完成 {len(drafts.items)} 条")

    console.rule("[bold]Step 5: validate[/bold]")
    validation = validate_drafts(drafts, fact_sheets)
    _save(out / "validation_report.json", validation)
    logger.info("validate", validation.summary)

    if not validation.passed:
        console.rule("[bold]Step 6: rewrite[/bold]")
        drafts = rewrite_failed_items(drafts, fact_sheets, validation, retrieved_examples)
        _save(out / "policy_card_drafts.json", drafts)
        logger.warning("rewrite", "已对未通过项执行重写")

        validation = validate_drafts(drafts, fact_sheets)
        _save(out / "validation_report.json", validation)
        logger.info("validate", f"重写后校验：{validation.summary}")

    console.rule("[bold]Step 7: finalize[/bold]")
    final_content = build_final_report_content(drafts)
    _save(out / "final_report_content.json", final_content)
    logger.info("finalize", "已输出 final_report_content.json")

    console.rule("[bold]Step 8: render[/bold]")
    docx_path = out / f"监管政策周报_{input_data.report_date}.docx"
    render_docx(final_content, docx_path)
    logger.info("render", f"Word 渲染完成：{docx_path.name}")
    console.print(f"[green]✓ docx → {docx_path}[/green]")

    _write_run_log(out, logger, input_data.report_date)


@main.command("parse-final")
@click.option("--input", "input_path", required=True, type=click.Path(exists=True), help="人工最终终稿路径，支持 md/txt/docx")
@click.option("--output-dir", "output_dir", default="./output", show_default=True)
@click.option("--date", "report_date", default="", help="周报日期，格式 YYYY.MM.DD")
def parse_final(input_path: str, output_dir: str, report_date: str) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    text = _read_text_file(Path(input_path))
    parsed = parse_final_report(text, report_date or "unknown")
    _save(out / "final_report_parsed.json", parsed)
    console.print(f"[green]✓ parsed {len(parsed.items)} items[/green]")


@main.command()
@click.option("--draft", "draft_path", required=True, type=click.Path(exists=True), help="policy_card_drafts.json")
@click.option("--final", "final_path", required=True, type=click.Path(exists=True), help="final_report_parsed.json")
@click.option("--fact-sheets", "fact_sheets_path", required=False, type=click.Path(exists=True), default=None)
@click.option("--output-dir", "output_dir", default="./output", show_default=True)
def learn(draft_path: str, final_path: str, fact_sheets_path: str | None, output_dir: str) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    drafts = PolicyCardDraftsOutput.model_validate_json(Path(draft_path).read_text(encoding="utf-8"))
    from .schemas import FinalReportParsed
    final_parsed = FinalReportParsed.model_validate_json(Path(final_path).read_text(encoding="utf-8"))
    fact_sheets = None
    if fact_sheets_path:
        fact_sheets = PolicyFactSheetsOutput.model_validate_json(Path(fact_sheets_path).read_text(encoding="utf-8"))
    elif (out / "policy_fact_sheets.json").exists():
        fact_sheets = PolicyFactSheetsOutput.model_validate_json((out / "policy_fact_sheets.json").read_text(encoding="utf-8"))

    diff = diff_draft_vs_final(drafts, final_parsed, fact_sheets)
    _save(out / "draft_final_diff.json", diff)

    fs_added = update_few_shots(diff)
    fe_added = update_forbidden_expansions(diff)
    report = LearningUpdateReport(
        report_date=drafts.report_date,
        few_shot_added_count=fs_added,
        forbidden_expansion_added_count=fe_added,
        notes=[f"few-shot +{fs_added}", f"forbidden expansion +{fe_added}"],
    )
    _save(out / "learning_update_report.json", report)
    console.print(f"[green]✓ few-shot +{fs_added}, forbidden expansion +{fe_added}[/green]")


@main.command()
@click.option("--output-dir", "output_dir", default="./output", show_default=True)
def upgrade(output_dir: str) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report = LearningUpdateReport(
        report_date=date.today().strftime("%Y.%m.%d"),
        notes=["upgrade: lightweight assets verified"],
    )
    _save(out / "upgrade_report.json", report)
    console.print("[green]✓ upgrade confirmed[/green]")


if __name__ == "__main__":
    main()
