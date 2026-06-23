import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.financials import build_financial_profile


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
