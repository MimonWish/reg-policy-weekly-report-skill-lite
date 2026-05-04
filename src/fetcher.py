from __future__ import annotations

import hashlib
import re
import time
from typing import Union
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from .schemas import FetchedArticle, FetchedArticlesOutput, NormalizedPoliciesOutput, WeeklyPoliciesInput

_OFFICIAL_DOMAINS = {
    "gov.cn",
    "www.gov.cn",
    "nfra.gov.cn",
    "cbirc.gov.cn",
    "pbc.gov.cn",
    "csrc.gov.cn",
    "safe.gov.cn",
    "mof.gov.cn",
    "ndrc.gov.cn",
    "nhc.gov.cn",
    "moj.gov.cn",
    "mofcom.gov.cn",
    "cac.gov.cn",
    "miit.gov.cn",
    "samr.gov.cn",
    "amac.org.cn",
    "sac.net.cn",
    "sse.com.cn",
    "szse.cn",
}

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; RegPolicyWeeklySkillLite/1.0)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
}


def _make_policy_id(issuer: str, title: str, date: str) -> str:
    raw = f"{issuer}|{title}|{date}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


def _make_title_display(issuer: str, title: str) -> str:
    if title.startswith(issuer):
        return title
    title_text = title if title.startswith("《") else f"《{title}》"
    return f"{issuer}{title_text}"


def _is_official_url(url: str) -> bool:
    try:
        hostname = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return any(hostname == d or hostname.endswith(f".{d}") for d in _OFFICIAL_DOMAINS)


def _clean_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript", "iframe"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    cleaned: list[str] = []
    for ln in lines:
        if len(ln) <= 1:
            continue
        if ln in cleaned[-3:]:
            continue
        cleaned.append(ln)
    return "\n".join(cleaned)


def _fetch_one(client: httpx.Client, article: FetchedArticle, retries: int = 2, timeout: float = 15.0) -> FetchedArticle:
    if not article.url.strip():
        return article.model_copy(
            update={
                "fetch_status": "title_only",
                "fetch_error": "empty url",
                "title_only_fallback": True,
                "metadata": {"reason": "empty url"},
            }
        )

    warning = "" if _is_official_url(article.url) else f"非官网链接: {article.url}"

    for attempt in range(retries + 1):
        try:
            resp = client.get(article.url, timeout=timeout, follow_redirects=True)
            resp.raise_for_status()
            raw_html = resp.text
            raw_text = _clean_text(raw_html)
            return article.model_copy(
                update={
                    "fetch_status": "success",
                    "raw_html": raw_html,
                    "raw_text": raw_text,
                    "official_link_warning": warning,
                    "metadata": {
                        "status_code": resp.status_code,
                        "final_url": str(resp.url),
                        "content_length": len(raw_html),
                    },
                }
            )
        except Exception as exc:
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            return article.model_copy(
                update={
                    "fetch_status": "title_only",
                    "fetch_error": str(exc),
                    "official_link_warning": warning,
                    "title_only_fallback": True,
                    "metadata": {"retries": retries, "timeout": timeout},
                }
            )


def fetch_articles(input_data: Union[WeeklyPoliciesInput, NormalizedPoliciesOutput]) -> FetchedArticlesOutput:
    articles: list[FetchedArticle] = []
    with httpx.Client(headers=_HEADERS) as client:
        for policy in input_data.policies:
            policy_id = _make_policy_id(policy.issuer, policy.title, policy.date)
            draft_article = FetchedArticle(
                policy_id=policy_id,
                issuer=policy.issuer,
                title=policy.title,
                title_display=_make_title_display(policy.issuer, policy.title),
                date=policy.date,
                url=policy.url,
                fetch_status="failed",
            )
            articles.append(_fetch_one(client, draft_article))

    return FetchedArticlesOutput(
        report_date=input_data.report_date,
        report_type="监管政策周报",
        articles=articles,
    )
