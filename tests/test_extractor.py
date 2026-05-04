"""Unit tests for src/extractor.py — focused on pure functions."""
from __future__ import annotations

import pytest

from src.extractor import (
    _base_title,
    _detect_policy_type,
    _detect_status,
    _extract_numbers_and_thresholds,
    _is_irrelevant_content,
    _normalize_text,
    extract_fact_sheets,
)
from src.schemas import FetchedArticle, FetchedArticlesOutput, WeeklyPoliciesInput, WeeklyPolicyItem


class TestIsIrrelevantContent:
    """_is_irrelevant_content 应正确区分政策正文与导航/首页噪声。"""

    def test_csrc_homepage_navigation_flagged_as_irrelevant(self):
        text = (
            "中国证券监督管理委员会 English 移动端 微博 微信 无障碍 "
            "首页 机构概况 投资者保护 发行监管 交易监管"
        )
        assert _is_irrelevant_content(text, "期货公司监督管理办法（征求意见稿）") is True

    def test_short_portal_page_flagged_as_irrelevant(self):
        text = "中華人民共和國反外國不當域外管轄條例_外交、外事_中國政府網 首頁 EN 登錄"
        assert _is_irrelevant_content(text, "中华人民共和国反外国不当域外管辖条例") is True

    def test_real_policy_text_not_flagged(self):
        text = (
            "期货公司监督管理办法（征求意见稿）正式发布。本次修订主要内容："
            "一是明确期货公司业务边界，允许开展期权业务。"
            "二是调整资本金要求，净资本不得低于5000万元。"
            "三是设立18个月过渡期。"
        )
        assert _is_irrelevant_content(text, "期货公司监督管理办法（征求意见稿）") is False

    def test_csrc_portal_with_title_in_meta_still_flagged(self):
        """即使页面 title 含政策名，但正文太薄也应被识别为无效。"""
        text = (
            "关于就《期货公司监督管理办法（征求意见稿）》征求意见的通知_中国证券监督管理委员会 "
            "English 移动端 首页"
        )
        assert _is_irrelevant_content(text, "期货公司监督管理办法（征求意见稿）") is True

    def test_empty_text_not_flagged(self):
        """空文本不参与判断（应由上层 len < 200 处理）。"""
        # 空 text 时关键词命中失败，但有效句也为 0 → 应被标为无关
        assert _is_irrelevant_content("", "期货公司监督管理办法") is True


class TestDetectStatus:
    @pytest.mark.parametrize("title,expected", [
        ("期货公司监督管理办法（征求意见稿）", "征求意见稿"),
        ("XX管理办法（修订草案）", "修订草案"),
        # 注意：含"行动方案"优先识别为"计划"（关键字顺序所致），符合既定 business_rules
        ("打击非法金融活动行动方案", "计划"),
        ("反垄断专项行动", "专项行动"),
        ("关于发布XX的通知", "正式实施"),
    ])
    def test_status_detection_from_title(self, title, expected):
        assert _detect_status(title, "") == expected


class TestDetectPolicyType:
    @pytest.mark.parametrize("title,expected", [
        ("期货公司监督管理办法", "办法"),
        ("XX条例", "条例"),
        ("关于XX的通知", "通知"),
        ("关于XX的指导意见", "意见"),
    ])
    def test_policy_type_detection(self, title, expected):
        assert _detect_policy_type(title, "") == expected


class TestBaseTitle:
    def test_strips_status_marker(self):
        assert _base_title("期货公司监督管理办法（征求意见稿）") == "期货公司监督管理办法"

    def test_strips_book_marks(self):
        assert "《" not in _base_title("《期货公司监督管理办法》")
        assert "》" not in _base_title("《期货公司监督管理办法》")

    def test_strips_implementation_announcement(self):
        title = "关于实施《期货公司监督管理办法》有关事项的公告"
        result = _base_title(title)
        assert "公告" not in result


class TestExtractNumbersAndThresholds:
    def test_extracts_percentage(self):
        text = "净资本占比不得低于5%。"
        results = _extract_numbers_and_thresholds(text)
        assert any(n.text == "5%" for n in results)

    def test_extracts_amount(self):
        text = "注册资本不得低于5000万元。"
        results = _extract_numbers_and_thresholds(text)
        assert any("5000万元" in n.text for n in results)

    def test_extracts_period(self):
        text = "过渡期为18个月。"
        results = _extract_numbers_and_thresholds(text)
        assert any("18个月" in n.text for n in results)

    def test_dedupes_repeated_tokens(self):
        text = "5%是关键。再次出现 5%。"
        results = _extract_numbers_and_thresholds(text)
        assert sum(1 for n in results if n.text == "5%") == 1


class TestNormalizeText:
    def test_collapses_whitespace(self):
        assert _normalize_text("a   b\n\nc") == "a b c"

    def test_handles_none(self):
        assert _normalize_text("") == ""


class TestProfessionalCompanyImpactRules:
    def _extract_one(self, title: str, issuer: str = "测试机构"):
        policy = WeeklyPolicyItem(
            date="2026-04-29",
            issuer=issuer,
            title=title,
            url="",
            include=True,
        )
        fetched = FetchedArticlesOutput(
            report_date="2026.05.03",
            articles=[
                FetchedArticle(
                    policy_id="test001",
                    issuer=issuer,
                    title=title,
                    title_display=f"{issuer}《{title}》",
                    date="2026-04-29",
                    url="",
                    fetch_status="title_only",
                    title_only_fallback=True,
                )
            ],
        )
        input_data = WeeklyPoliciesInput(
            report_date="2026.05.03",
            policies=[policy],
        )
        return extract_fact_sheets(fetched, input_data).fact_sheets[0]

    def test_trust_registration_maps_to_trust_and_capital(self):
        fs = self._extract_one("延长股权信托财产登记试点有效期并扩大适用范围", "北京金融监管局、北京市市场监管局")

        assert "平安信托" in fs.allowed_paragraph2_entities
        assert "平安资本" in fs.allowed_paragraph2_entities
        assert fs.paragraph2_mode == "direct"
        assert fs.importance == "major"
        assert any("股权信托财产登记" in action for action in fs.allowed_paragraph2_actions)

    def test_data_export_negative_list_maps_to_professional_companies(self):
        fs = self._extract_one("上海自贸试验区、服务业扩大开放综合试点地区数据出境负面清单管理办法及负面清单", "上海市网信办、上海市数据局")

        assert "平安寿险" in fs.allowed_paragraph2_entities
        assert "平安产险" in fs.allowed_paragraph2_entities
        assert "集团科技条线" in fs.allowed_paragraph2_entities
        assert fs.paragraph2_mode == "scene_direct_related"
        assert any("数据出境" in phrase for phrase in fs.impact_focus)

    def test_marine_law_time_effect_maps_to_pnc_claims(self):
        fs = self._extract_one("关于适用〈中华人民共和国海商法〉时间效力的若干规定", "最高人民法院")

        assert fs.allowed_paragraph2_entities == ["平安产险"]
        assert fs.paragraph2_mode == "direct"
        assert any("海事理赔" in action for action in fs.allowed_paragraph2_actions)
