import os
import re
from functools import lru_cache

import requests


SEC_HEADERS = {
    "User-Agent": os.getenv("SEC_USER_AGENT", "DeepAlpha research prototype contact@example.com"),
    "Accept-Encoding": "gzip, deflate",
}
SEC_TIMEOUT_SECONDS = float(os.getenv("SEC_TIMEOUT_SECONDS", "20"))
SEC_TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

US_EXCHANGES = {"", "NASDAQ", "NYSE", "AMEX", "OTC", "NYSEARCA", "BATS"}
PERIODIC_REPORT_FORMS = {"10-K", "10-Q", "20-F", "40-F"}
FOREIGN_ISSUER_UPDATE_FORMS = {"6-K"}


def normalize_us_ticker(symbol: str | None, exchange: str | None = None) -> str:
    value = (symbol or "").strip().upper()
    if not value:
        return ""

    if ":" in value:
        prefix, value = value.split(":", 1)
        exchange = exchange or prefix

    value = value.split(".", 1)[0].strip()
    clean_exchange = (exchange or "").strip().upper()
    if clean_exchange and clean_exchange not in US_EXCHANGES:
        return ""

    if not re.fullmatch(r"[A-Z0-9-]{1,8}", value):
        return ""
    return value


@lru_cache(maxsize=1)
def _ticker_map() -> dict[str, dict]:
    response = requests.get(SEC_TICKER_URL, headers=SEC_HEADERS, timeout=SEC_TIMEOUT_SECONDS)
    response.raise_for_status()
    raw_data = response.json()
    return {item["ticker"].upper(): item for item in raw_data.values()}


def ticker_to_cik(ticker: str) -> dict:
    normalized = normalize_us_ticker(ticker)
    if not normalized:
        return {"matched": False, "ticker": ticker, "reason": "SEC companyfacts currently supports US tickers only."}

    item = _ticker_map().get(normalized)
    if not item:
        return {"matched": False, "ticker": normalized, "reason": "Ticker not found in SEC company tickers."}

    cik = str(item["cik_str"]).zfill(10)
    return {
        "matched": True,
        "ticker": normalized,
        "cik": cik,
        "company_name": item.get("title", ""),
    }


def get_companyfacts(cik: str) -> dict:
    response = requests.get(
        SEC_COMPANYFACTS_URL.format(cik=str(cik).zfill(10)),
        headers=SEC_HEADERS,
        timeout=SEC_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def get_latest_filing_metadata(cik: str) -> dict:
    response = requests.get(
        SEC_SUBMISSIONS_URL.format(cik=str(cik).zfill(10)),
        headers=SEC_HEADERS,
        timeout=SEC_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()
    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    report_dates = recent.get("reportDate", [])
    filing_dates = recent.get("filingDate", [])
    primary_documents = recent.get("primaryDocument", [])

    def filing_at(index: int, form: str) -> dict:
        accession = accessions[index] if index < len(accessions) else ""
        accession_path = accession.replace("-", "")
        primary_doc = primary_documents[index] if index < len(primary_documents) else ""
        filing_url = ""
        if accession and primary_doc:
            filing_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_path}/{primary_doc}"

        return {
            "form": form,
            "accession_number": accession,
            "report_date": report_dates[index] if index < len(report_dates) else "",
            "filing_date": filing_dates[index] if index < len(filing_dates) else "",
            "filing_url": filing_url,
        }

    for accepted_forms in (PERIODIC_REPORT_FORMS, FOREIGN_ISSUER_UPDATE_FORMS):
        for index, form in enumerate(forms):
            if form in accepted_forms:
                return filing_at(index, form)

    return {}
