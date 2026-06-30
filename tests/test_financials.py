import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.financials import _pivot_hk_row_records, build_financial_profile


class Frame:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.empty = not rows

    def to_dict(self, orient: str) -> list[dict]:
        assert orient == "records"
        return self.rows


def test_cn_financial_profile_uses_akshare_summary_and_announcements(monkeypatch) -> None:
    fake_akshare = SimpleNamespace(
        stock_financial_analysis_indicator_em=lambda symbol, indicator="按报告期": Frame(
            [
                {
                    "REPORT_DATE": "2026-03-31",
                    "TOTAL_OPERATE_INCOME": 1_506_000_000,
                    "PARENT_NETPROFIT": 756_000_000,
                    "GROSS_PROFIT_RATIO": 91.3,
                    "NETPROFIT_MARGIN": 50.2,
                    "ROE_WEIGHT": 31.5,
                    "DEBT_ASSET_RATIO": 25.4,
                    "NETCASH_OPERATE": 650_000_000,
                }
            ]
        ),
        stock_cash_flow_sheet_by_report_em=lambda symbol: Frame([]),
        stock_balance_sheet_by_report_em=lambda symbol: Frame(
            [
                {
                    "REPORT_DATE": "2026-03-31",
                    "MONETARYFUNDS": 800_000_000,
                    "SHORT_LOAN": 50_000_000,
                    "LONG_LOAN": 100_000_000,
                    "TOTAL_ASSETS": 2_500_000_000,
                    "TOTAL_LIABILITIES": 635_000_000,
                    "TOTAL_PARENT_EQUITY": 1_865_000_000,
                }
            ]
        ),
        stock_profit_sheet_by_report_em=lambda symbol: Frame(
            [
                {
                    "REPORT_DATE": "2026-03-31",
                    "DILUTED_EPS": 12.5,
                    "OPERATE_PROFIT": 1_100_000_000,
                }
            ]
        ),
        stock_individual_notice_report=lambda security, symbol="财务报告", begin_date=None, end_date=None: Frame(
            [
                {
                    "公告日期": "2026-04-30",
                    "公告标题": "贵州茅台2026年第一季度报告",
                    "公告链接": "https://data.eastmoney.com/notices/detail/600519/report.html",
                    "公告类型": "财务报告",
                }
            ]
        ),
    )
    monkeypatch.setattr("app.services.financials._akshare_module", lambda: fake_akshare, raising=False)

    profile = build_financial_profile("600519", "SSE")

    assert profile["enabled"] is True
    assert profile["context_status"] == "available"
    assert profile["market"] == "cn"
    assert profile["symbol"] == "SH600519"
    assert profile["source"] == "akshare_cn"
    assert profile["currency"] == "CNY"
    assert profile["revenue"] == 1_506_000_000
    assert profile["net_income"] == 756_000_000
    assert profile["gross_margin_percent"] == 91.3
    assert profile["net_margin_percent"] == 50.2
    assert profile["roe_percent"] == 31.5
    assert profile["debt_to_asset_percent"] == 25.4
    assert profile["operating_cash_flow"] == 650_000_000
    assert profile["eps_diluted"] == 12.5
    assert profile["operating_income"] == 1_100_000_000
    assert profile["cash"] == 800_000_000
    assert profile["debt"] == 150_000_000
    assert profile["total_assets"] == 2_500_000_000
    assert profile["total_liabilities"] == 635_000_000
    assert profile["shareholders_equity"] == 1_865_000_000
    assert profile["short_term_debt"] == 50_000_000
    assert profile["long_term_debt"] == 100_000_000
    assert profile["announcements"][0]["url"].startswith("https://data.eastmoney.com/")
    assert profile["filing_url"] == profile["announcements"][0]["url"]


def test_cn_financial_profile_fetch_failure_is_explicit(monkeypatch) -> None:
    def raise_timeout(*args, **kwargs):
        raise TimeoutError("akshare timed out")

    fake_akshare = SimpleNamespace(stock_financial_analysis_indicator_em=raise_timeout)
    monkeypatch.setattr("app.services.financials._akshare_module", lambda: fake_akshare, raising=False)

    profile = build_financial_profile("600519", "SSE")

    assert profile["enabled"] is False
    assert profile["context_status"] == "fetch_failed"
    assert profile["source"] == "akshare_cn"
    assert profile["reason"] == "TimeoutError"
    assert "mock" not in str(profile).lower()


def test_hk_financial_profile_marks_partial_when_only_announcements_exist(monkeypatch) -> None:
    fake_akshare = SimpleNamespace(
        stock_financial_hk_analysis_indicator_em=lambda symbol, indicator="年度": Frame([]),
        stock_financial_hk_report_em=lambda stock, symbol="现金流量表", indicator="年度": Frame([]),
        stock_individual_notice_report=lambda security, symbol="财务报告", begin_date=None, end_date=None: Frame(
            [
                {
                    "公告日期": "2026-03-20",
                    "公告标题": "腾讯控股 年度业绩公告",
                    "公告链接": "https://data.eastmoney.com/notices/detail/00700/annual.html",
                    "公告类型": "财务报告",
                }
            ]
        ),
    )
    monkeypatch.setattr("app.services.financials._akshare_module", lambda: fake_akshare, raising=False)

    profile = build_financial_profile("0700.HK", "HKEX")

    assert profile["enabled"] is True
    assert profile["context_status"] == "partial"
    assert profile["market"] == "hk"
    assert profile["symbol"] == "HK00700"
    assert profile["source"] == "akshare_hk"
    assert profile["revenue"] is None
    assert "revenue" in profile["missing_fields"]
    assert profile["announcements"][0]["title"] == "腾讯控股 年度业绩公告"
    assert profile["filing_url"] == profile["announcements"][0]["url"]


def test_hk_financial_profile_returns_missing_when_akshare_has_no_data(monkeypatch) -> None:
    fake_akshare = SimpleNamespace(
        stock_financial_hk_analysis_indicator_em=lambda symbol, indicator="年度": Frame([]),
        stock_financial_hk_report_em=lambda stock, symbol="现金流量表", indicator="年度": Frame([]),
        stock_individual_notice_report=lambda security, symbol="财务报告", begin_date=None, end_date=None: Frame([]),
    )
    monkeypatch.setattr("app.services.financials._akshare_module", lambda: fake_akshare, raising=False)

    profile = build_financial_profile("0700.HK", "HKEX")

    assert profile["enabled"] is False
    assert profile["context_status"] == "missing"
    assert profile["source"] == "akshare_hk"
    assert profile["reason"] == "No AkShare financial or announcement records returned."


def test_us_financial_profile_keeps_sec_companyfacts_source(monkeypatch) -> None:
    companyfacts = {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [
                            {
                                "val": 100,
                                "form": "10-Q",
                                "fy": 2026,
                                "fp": "Q1",
                                "end": "2026-03-31",
                                "filed": "2026-04-30",
                                "start": "2026-01-01",
                            }
                        ]
                    }
                }
            }
        }
    }
    monkeypatch.setattr(
        "app.services.financials.ticker_to_cik",
        lambda ticker: {"matched": True, "ticker": ticker, "cik": "0000000001", "company_name": "US Co"},
    )
    monkeypatch.setattr("app.services.financials.get_companyfacts", lambda cik: companyfacts)
    monkeypatch.setattr(
        "app.services.financials.get_latest_filing_metadata",
        lambda cik: {
            "form": "10-Q",
            "report_date": "2026-03-31",
            "filing_date": "2026-04-30",
            "filing_url": "https://www.sec.gov/test.htm",
        },
    )

    profile = build_financial_profile("AAPL", "NASDAQ")

    assert profile["enabled"] is True
    assert profile["source"] == "sec_companyfacts"
    assert profile["symbol"] == "AAPL"
    assert profile["revenue"] == 100


def test_cn_yoy_change_when_prior_period_exists(monkeypatch) -> None:
    fake_akshare = SimpleNamespace(
        stock_financial_analysis_indicator_em=lambda symbol, indicator="按报告期": Frame(
            [
                {
                    "REPORT_DATE": "2026-03-31",
                    "TOTAL_OPERATE_INCOME": 1_500_000_000,
                    "PARENT_NETPROFIT": 750_000_000,
                    "GROSS_PROFIT_RATIO": 90.0,
                    "NETPROFIT_MARGIN": 50.0,
                    "ROE_WEIGHT": 30.0,
                    "DEBT_ASSET_RATIO": 25.0,
                    "NETCASH_OPERATE": 600_000_000,
                },
                {
                    "REPORT_DATE": "2025-03-31",
                    "TOTAL_OPERATE_INCOME": 1_200_000_000,
                    "PARENT_NETPROFIT": 600_000_000,
                    "GROSS_PROFIT_RATIO": 88.0,
                    "NETPROFIT_MARGIN": 48.0,
                    "ROE_WEIGHT": 28.0,
                    "DEBT_ASSET_RATIO": 27.0,
                    "NETCASH_OPERATE": 500_000_000,
                },
            ]
        ),
        stock_cash_flow_sheet_by_report_em=lambda symbol: Frame([]),
        stock_balance_sheet_by_report_em=lambda symbol: Frame([]),
        stock_profit_sheet_by_report_em=lambda symbol: Frame([]),
        stock_individual_notice_report=lambda security, symbol="财务报告", begin_date=None, end_date=None: Frame(
            [{"公告日期": "2026-04-30", "公告标题": "Q1 Report", "公告链接": "https://example.com/report", "公告类型": "财务报告"}]
        ),
    )
    monkeypatch.setattr("app.services.financials._akshare_module", lambda: fake_akshare, raising=False)

    profile = build_financial_profile("600519", "SSE")

    assert profile["enabled"] is True
    assert profile["revenue"] == 1_500_000_000
    assert profile["revenue_change_percent"] == 25.0  # (1500-1200)/1200*100
    assert profile["net_income"] == 750_000_000
    assert profile["net_income_change_percent"] == 25.0  # (750-600)/600*100
    assert profile["operating_cash_flow"] == 600_000_000
    assert profile["operating_cash_flow_change_percent"] == 20.0  # (600-500)/500*100


def test_cn_announcement_classification(monkeypatch) -> None:
    fake_akshare = SimpleNamespace(
        stock_financial_analysis_indicator_em=lambda symbol, indicator="按报告期": Frame(
            [{"REPORT_DATE": "2026-03-31", "TOTAL_OPERATE_INCOME": 1_000_000, "PARENT_NETPROFIT": 500_000}]
        ),
        stock_cash_flow_sheet_by_report_em=lambda symbol: Frame([]),
        stock_balance_sheet_by_report_em=lambda symbol: Frame([]),
        stock_profit_sheet_by_report_em=lambda symbol: Frame([]),
        stock_individual_notice_report=lambda security, symbol="财务报告", begin_date=None, end_date=None: Frame(
            [
                {"公告日期": "2026-04-15", "公告标题": "2025年度报告", "公告链接": "https://eastmoney.com/notice/1", "公告类型": "财务报告"},
            ]
            if symbol == "财务报告"
            else (
                [
                    {"公告日期": "2026-03-10", "公告标题": "2025年度业绩预告", "公告链接": "https://eastmoney.com/notice/2", "公告类型": "业绩预告"},
                ]
                if symbol == "重大事项"
                else Frame([])
            )
        ),
    )
    monkeypatch.setattr("app.services.financials._akshare_module", lambda: fake_akshare, raising=False)

    profile = build_financial_profile("600519", "SSE")

    assert profile["enabled"] is True
    announcements = profile["announcements"]
    # Should have both announcements (from different types)
    assert len(announcements) >= 1
    # The financial report should be classified correctly
    fin_reports = [a for a in announcements if a["classified_type"] == "financial_report"]
    assert len(fin_reports) >= 1
    assert any("年度报告" in a["title"] for a in fin_reports)
    # Announcement summary should exist
    ann_summary = profile.get("announcement_summary", {})
    assert "financial_report" in ann_summary


def test_cn_graceful_degradation_when_new_sources_fail(monkeypatch) -> None:
    """Balance sheet and profit sheet failures should not block the profile."""
    fake_akshare = SimpleNamespace(
        stock_financial_analysis_indicator_em=lambda symbol, indicator="按报告期": Frame(
            [{"REPORT_DATE": "2026-03-31", "TOTAL_OPERATE_INCOME": 1_000_000, "PARENT_NETPROFIT": 500_000}]
        ),
        stock_cash_flow_sheet_by_report_em=lambda symbol: Frame([]),
        stock_balance_sheet_by_report_em=lambda symbol: (_ for _ in ()).throw(TimeoutError("balance sheet timeout")),
        stock_profit_sheet_by_report_em=lambda symbol: (_ for _ in ()).throw(TimeoutError("profit sheet timeout")),
        stock_individual_notice_report=lambda security, symbol="财务报告", begin_date=None, end_date=None: Frame([]),
    )
    monkeypatch.setattr("app.services.financials._akshare_module", lambda: fake_akshare, raising=False)

    profile = build_financial_profile("600519", "SSE")

    # Should still return a profile with indicator data
    assert profile["enabled"] is True
    assert profile["revenue"] == 1_000_000
    assert profile["net_income"] == 500_000
    # Balance sheet fields should remain None but not crash
    assert profile["cash"] is None
    assert profile["debt"] is None
    assert profile["shareholders_equity"] is None


def test_hk_pivot_row_records(monkeypatch) -> None:
    """HK balance sheet row records should be pivoted to column-oriented format."""
    records = [
        {"STD_ITEM_NAME": "资产总额", "AMOUNT": 5_000_000_000, "REPORT_DATE": "2026-03-31"},
        {"STD_ITEM_NAME": "现金及现金等价物", "AMOUNT": 800_000_000, "REPORT_DATE": "2026-03-31"},
        {"STD_ITEM_NAME": "短期借款", "AMOUNT": 200_000_000, "REPORT_DATE": "2026-03-31"},
        {"STD_ITEM_NAME": "长期借款", "AMOUNT": 500_000_000, "REPORT_DATE": "2026-03-31"},
        {"STD_ITEM_NAME": "股东权益", "AMOUNT": 3_000_000_000, "REPORT_DATE": "2026-03-31"},
        {"STD_ITEM_NAME": "资产总额", "AMOUNT": 4_500_000_000, "REPORT_DATE": "2025-03-31"},
        {"STD_ITEM_NAME": "现金及现金等价物", "AMOUNT": 700_000_000, "REPORT_DATE": "2025-03-31"},
    ]

    result = _pivot_hk_row_records(records)

    assert len(result) == 2  # Two periods
    # Find the 2026 record
    r2026 = next(r for r in result if r["REPORT_DATE"] == "2026-03-31")
    assert r2026["total_assets"] == 5_000_000_000
    assert r2026["cash"] == 800_000_000
    assert r2026["short_term_debt"] == 200_000_000
    assert r2026["long_term_debt"] == 500_000_000
    assert r2026["shareholders_equity"] == 3_000_000_000


def test_cn_management_guidance_fields_exist(monkeypatch) -> None:
    """Profile should include management_guidance, announcement_summary, and capital_flow_context fields."""
    fake_akshare = SimpleNamespace(
        stock_financial_analysis_indicator_em=lambda symbol, indicator="按报告期": Frame(
            [{"REPORT_DATE": "2026-03-31", "TOTAL_OPERATE_INCOME": 1_000_000, "PARENT_NETPROFIT": 500_000}]
        ),
        stock_cash_flow_sheet_by_report_em=lambda symbol: Frame([]),
        stock_balance_sheet_by_report_em=lambda symbol: Frame([]),
        stock_profit_sheet_by_report_em=lambda symbol: Frame([]),
        stock_individual_notice_report=lambda security, symbol="财务报告", begin_date=None, end_date=None: Frame([]),
    )
    monkeypatch.setattr("app.services.financials._akshare_module", lambda: fake_akshare, raising=False)

    profile = build_financial_profile("600519", "SSE")

    # New fields should always exist (at least with defaults)
    assert "management_guidance" in profile
    assert "announcement_summary" in profile
    assert "dividends" in profile
    assert "capital_flow_context" in profile
    assert "short_term_debt" in profile
    assert "long_term_debt" in profile


def test_hk_yoy_change_when_prior_period_exists(monkeypatch) -> None:
    """HK YoY: _build_hk_financial_profile should pass prev_values for revenue/net_income/OCF change %."""
    fake_akshare = SimpleNamespace(
        stock_financial_hk_analysis_indicator_em=lambda symbol, indicator="年度": Frame(
            [
                {
                    "REPORT_DATE": "2026-03-31",
                    "OPERATE_INCOME": 660_000_000_000,
                    "HOLDER_PROFIT": 200_000_000_000,
                    "GROSS_PROFIT_RATIO": 53.0,
                    "NET_PROFIT_RATIO": 30.0,
                    "ROE_AVG": 22.0,
                    "DEBT_ASSET_RATIO": 41.0,
                    "BASIC_EPS": 21.0,
                    "DILUTED_EPS": 20.5,
                },
                {
                    "REPORT_DATE": "2025-03-31",
                    "OPERATE_INCOME": 600_000_000_000,
                    "HOLDER_PROFIT": 180_000_000_000,
                    "GROSS_PROFIT_RATIO": 52.0,
                    "NET_PROFIT_RATIO": 29.0,
                    "ROE_AVG": 20.0,
                    "DEBT_ASSET_RATIO": 43.0,
                    "BASIC_EPS": 19.0,
                    "DILUTED_EPS": 18.5,
                },
            ]
        ),
        stock_financial_hk_report_em=lambda stock, symbol="现金流量表", indicator="年度": Frame([]),
        stock_individual_notice_report=lambda security, symbol="财务报告", begin_date=None, end_date=None: Frame(
            [{"公告日期": "2026-04-30", "公告标题": "腾讯 年度业绩公告", "公告链接": "https://data.eastmoney.com/notices/detail/00700/test.html", "公告类型": "财务报告"}]
        ),
    )
    monkeypatch.setattr("app.services.financials._akshare_module", lambda: fake_akshare, raising=False)
    # Stub out yfinance calls for this test — avoid real network
    monkeypatch.setattr(
        "app.services.financials._fetch_hk_yfinance_context",
        lambda symbol: {"enabled": False, "source": "yfinance", "warnings": ["test stub"]},
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.financials._build_hk_segment_data",
        lambda yf_ctx: {"enabled": False, "source": "", "warnings": []},
        raising=False,
    )

    profile = build_financial_profile("0700.HK", "HKEX")

    assert profile["enabled"] is True
    assert profile["revenue"] == 660_000_000_000
    assert profile["net_income"] == 200_000_000_000
    assert profile["revenue_change_percent"] == 10.0  # (660B - 600B) / 600B * 100
    assert profile["net_income_change_percent"] == pytest.approx(11.111, abs=0.01)  # (200B - 180B) / 180B * 100
    assert profile["eps_diluted"] == 20.5
    assert profile["gross_margin_percent"] == 53.0
    assert profile["roe_percent"] == 22.0


def test_hk_segment_data_qualitative_when_yfinance_available(monkeypatch) -> None:
    """HK segment_data should be qualitative (quantitative=False) with yfinance context."""
    fake_akshare = SimpleNamespace(
        stock_financial_hk_analysis_indicator_em=lambda symbol, indicator="年度": Frame(
            [{"REPORT_DATE": "2026-03-31", "OPERATE_INCOME": 660_000_000_000, "HOLDER_PROFIT": 200_000_000_000}]
        ),
        stock_financial_hk_report_em=lambda stock, symbol="现金流量表", indicator="年度": Frame([]),
        stock_individual_notice_report=lambda security, symbol="财务报告", begin_date=None, end_date=None: Frame(
            [{"公告日期": "2026-04-30", "公告标题": "腾讯 年度业绩公告", "公告链接": "https://example.com/test", "公告类型": "财务报告"}]
        ),
    )
    monkeypatch.setattr("app.services.financials._akshare_module", lambda: fake_akshare, raising=False)
    monkeypatch.setattr(
        "app.services.financials._fetch_hk_yfinance_context",
        lambda symbol: {
            "enabled": True,
            "source": "yfinance",
            "business_summary": "Tencent provides value-added services, fintech, and business services.",
            "sector": "Communication Services",
            "industry": "Internet Content & Information",
            "qualitative_segments": ["value-added services", "fintech", "business services"],
            "revenue_growth": 0.091,
            "earnings_growth": 0.229,
            "operating_margins": 0.343,
            "warnings": [],
        },
        raising=False,
    )
    # _build_hk_segment_data runs with real logic — processes the yfinance mock above

    profile = build_financial_profile("0700.HK", "HKEX")

    assert profile["enabled"] is True
    assert profile["revenue"] == 660_000_000_000
    assert profile["revenue_change_percent"] is None  # Only one period, no YoY
    assert profile["yfinance_context"]["enabled"] is True
    assert "Tencent" in profile["yfinance_context"]["business_summary"]

    seg = profile["segment_data"]
    assert seg["enabled"] is True
    assert seg["quantitative"] is False
    assert seg["source"] == "yfinance_business_summary"
    assert "value-added services" in seg["qualitative_segments"]
    assert "fintech" in seg["qualitative_segments"]
    assert seg["sector"] == "Communication Services"
    assert seg["industry"] == "Internet Content & Information"


def test_hk_yfinance_context_graceful_failure(monkeypatch) -> None:
    """HK profile should build successfully even when yfinance is unavailable."""
    fake_akshare = SimpleNamespace(
        stock_financial_hk_analysis_indicator_em=lambda symbol, indicator="年度": Frame(
            [{"REPORT_DATE": "2026-03-31", "OPERATE_INCOME": 660_000_000_000, "HOLDER_PROFIT": 200_000_000_000}]
        ),
        stock_financial_hk_report_em=lambda stock, symbol="现金流量表", indicator="年度": Frame([]),
        stock_individual_notice_report=lambda security, symbol="财务报告", begin_date=None, end_date=None: Frame(
            [{"公告日期": "2026-04-30", "公告标题": "腾讯 年度业绩公告", "公告链接": "https://example.com/test", "公告类型": "财务报告"}]
        ),
    )
    monkeypatch.setattr("app.services.financials._akshare_module", lambda: fake_akshare, raising=False)
    # Simulate yfinance import failure
    monkeypatch.setattr(
        "app.services.financials._fetch_hk_yfinance_context",
        lambda symbol: {"enabled": False, "source": "yfinance", "warnings": ["yfinance not available"]},
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.financials._build_hk_segment_data",
        lambda yf_ctx: {"enabled": False, "source": "", "warnings": yf_ctx.get("warnings", [])},
        raising=False,
    )

    profile = build_financial_profile("0700.HK", "HKEX")

    # Must still build successfully
    assert profile["enabled"] is True
    assert profile["revenue"] == 660_000_000_000
    assert profile["yfinance_context"]["enabled"] is False
    assert "yfinance not available" in profile["yfinance_context"]["warnings"]
    # segment_data should be disabled
    assert profile["segment_data"]["enabled"] is False
