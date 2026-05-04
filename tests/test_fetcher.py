from __future__ import annotations

from src.fetcher import _make_title_display


def test_title_display_does_not_double_wrap_book_title_with_suffix() -> None:
    assert (
        _make_title_display("全国人大常委会", "《中华人民共和国监狱法》修订版")
        == "全国人大常委会《中华人民共和国监狱法》修订版"
    )


def test_title_display_wraps_plain_title() -> None:
    assert (
        _make_title_display("北京金融监管局", "延长股权信托财产登记试点有效期")
        == "北京金融监管局《延长股权信托财产登记试点有效期》"
    )
