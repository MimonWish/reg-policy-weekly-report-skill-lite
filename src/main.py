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
from .generator import (
    build_final_report_content,
    build_generation_prompt,
    generate_drafts,
    retrieve_examples,
    rewrite_failed_items,
)
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
    """[legacy] 在 Python 子进程内自调 anthropic SDK 一条龙生成 docx。

    需要 ANTHROPIC_API_KEY 环境变量。新项目推荐使用 prepare + finalize 模式。
    """
    console.print("[yellow]⚠ legacy 模式：建议使用 prepare + finalize 替代（无需 API key）。[/yellow]")
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


@main.command()
@click.option("--input", "input_path", required=True, type=click.Path(exists=True), help="weekly_policies.json 路径")
@click.option("--output-dir", "output_dir", default="./output", show_default=True, help="输出目录")
def prepare(input_path: str, output_dir: str) -> None:
    """Skill-as-instructions 模式 Stage A：准备事实卡和提示词，由会话 LLM 接管生成。

    本命令不调用任何 LLM API，仅做规则提取和数据汇总。
    产物：fact_sheets / retrieved_examples / generation_prompt.md
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    logger = _RunLogger()

    raw = Path(input_path).read_text(encoding="utf-8")
    input_data = WeeklyPoliciesInput.model_validate_json(raw)
    logger.info("input", f"读取输入，共 {len(input_data.policies)} 条")

    console.rule("[bold]Stage A · Step 0: normalize[/bold]")
    normalized = _normalize(input_data)
    _save(out / "normalized_policies.json", normalized)
    logger.info("normalize", f"过滤去重后保留 {len(normalized.policies)} 条")

    console.rule("[bold]Stage A · Step 1: fetch[/bold]")
    fetched = fetch_articles(normalized)
    _save(out / "fetched_articles.json", fetched)
    fallback_count = sum(1 for a in fetched.articles if a.title_only_fallback)
    logger.info("fetch", f"抓取完成 {len(fetched.articles)} 条，title_only fallback={fallback_count}")

    console.rule("[bold]Stage A · Step 2: extract（仅规则，不调 LLM）[/bold]")
    fact_sheets = extract_fact_sheets(fetched, normalized, client=None)
    _save(out / "policy_fact_sheets.json", fact_sheets)
    logger.info("extract", f"事实卡构建完成 {len(fact_sheets.fact_sheets)} 条")

    console.rule("[bold]Stage A · Step 3: retrieve few-shot[/bold]")
    retrieved = retrieve_examples(fact_sheets)
    _save(out / "retrieved_examples.json", retrieved)
    logger.info("fewshot", "few-shot 检索完成")

    console.rule("[bold]Stage A · Step 4: build generation prompt[/bold]")
    prompt_text = build_generation_prompt(fact_sheets, retrieved)
    prompt_path = out / "generation_prompt.md"
    prompt_path.write_text(prompt_text, encoding="utf-8")
    console.print(f"  [dim]saved → {prompt_path}[/dim]")
    logger.info("prompt", f"生成提示词 {len(prompt_text)} 字符")

    _write_run_log(out, logger, input_data.report_date)

    console.print()
    console.print("[bold green]Stage A 完成。[/bold green]")
    console.print()
    console.print("[bold]下一步（Stage B）：[/bold]")
    console.print(f"  1. 让会话 LLM 读取 [cyan]{prompt_path}[/cyan]")
    console.print(f"  2. LLM 按提示词产出 JSON，写入 [cyan]{out / 'policy_card_drafts.json'}[/cyan]")
    console.print(f"  3. 运行 [cyan]python -m src.main finalize --output-dir {output_dir}[/cyan]")


@main.command()
@click.option("--output-dir", "output_dir", default="./output", show_default=True, help="包含 policy_card_drafts.json 的目录")
def finalize(output_dir: str) -> None:
    """Skill-as-instructions 模式 Stage C：校验 + 渲染 docx。

    需要 Stage B 由会话 LLM 写好 policy_card_drafts.json 之后再运行。
    """
    out = Path(output_dir)
    drafts_path = out / "policy_card_drafts.json"
    fact_sheets_path = out / "policy_fact_sheets.json"
    if not drafts_path.exists():
        console.print(f"[red]错误：找不到 {drafts_path}[/red]")
        console.print("  请先让会话 LLM 按 generation_prompt.md 产出 drafts JSON 后再运行 finalize。")
        raise SystemExit(1)
    if not fact_sheets_path.exists():
        console.print(f"[red]错误：找不到 {fact_sheets_path}[/red]")
        console.print("  请先运行 [cyan]python -m src.main prepare[/cyan]。")
        raise SystemExit(1)

    logger = _RunLogger()
    drafts = PolicyCardDraftsOutput.model_validate_json(drafts_path.read_text(encoding="utf-8"))
    fact_sheets = PolicyFactSheetsOutput.model_validate_json(fact_sheets_path.read_text(encoding="utf-8"))
    logger.info("input", f"读取 drafts {len(drafts.items)} 条 + fact_sheets {len(fact_sheets.fact_sheets)} 条")

    console.rule("[bold]Stage C · Step 5: validate[/bold]")
    validation = validate_drafts(drafts, fact_sheets)
    _save(out / "validation_report.json", validation)
    logger.info("validate", validation.summary)
    if not validation.passed:
        console.print(f"[yellow][!] 校验未全通过：{validation.summary}[/yellow]")
        console.print("  失败项已记录在 validation_report.json，请人工审阅或回 Stage B 重新生成对应条目。")

    console.rule("[bold]Stage C · Step 6: finalize[/bold]")
    final_content = build_final_report_content(drafts)
    _save(out / "final_report_content.json", final_content)
    logger.info("finalize", "已输出 final_report_content.json")

    console.rule("[bold]Stage C · Step 7: render[/bold]")
    docx_path = out / f"监管政策周报_{drafts.report_date}.docx"
    render_docx(final_content, docx_path)
    logger.info("render", f"Word 渲染完成：{docx_path.name}")
    console.print(f"[green]✓ docx → {docx_path}[/green]")

    _write_run_log(out, logger, drafts.report_date)


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
