"""Collect source documents into data/sources/.

Web pages and PDFs: `scg collect url` fetches one document, caches its text
and registers it (safe to run in parallel).

SEC filings: the latest annual report (10-K or 20-F) for each row of
data/sources/sec_targets.csv is downloaded from EDGAR, converted to plain text
at data/sources/cache/<source_id>.txt, and registered in sources.csv.
"""

import csv
import datetime as dt
import fcntl
import hashlib
import io
import os
import re
import time
import warnings
from contextlib import contextmanager
from pathlib import Path

import httpx
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from pypdf import PdfReader

from scg import paths

SOURCE_FIELDS = ["id", "url", "title", "publisher", "company", "doc_type", "published", "retrieved", "sha256"]


def html_to_text(html: str) -> str:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)  # iXBRL filings are XHTML
        soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "ix:header"]):
        tag.decompose()
    for tag in soup.find_all(style=re.compile(r"display:\s*none")):
        tag.decompose()
    # Break lines only at block elements; inline spans (iXBRL wraps every number) stay joined.
    for tag in soup.find_all(["p", "div", "br", "li", "tr", "table", "h1", "h2", "h3", "h4", "h5", "h6"]):
        tag.append("\n")
    for tag in soup.find_all(["td", "th"]):
        tag.append(" ")
    text = soup.get_text("")
    lines = (re.sub(r"[ \t ]+", " ", line).strip() for line in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"


def read_sources(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    with path.open(newline="") as f:
        return {row["id"]: row for row in csv.DictReader(f)}


def write_sources(path: Path, rows: dict[str, dict]) -> None:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SOURCE_FIELDS)
        w.writeheader()
        for sid in sorted(rows):
            w.writerow({k: rows[sid].get(k, "") for k in SOURCE_FIELDS})


@contextmanager
def _locked(path: Path):
    """Exclusive lock so parallel collectors don't clobber sources.csv."""
    with (path.parent / f".{path.name}.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def register_sources(new_rows: list[dict], path: Path | None = None) -> None:
    path = path or paths.SOURCES_DIR / "sources.csv"
    with _locked(path):
        rows = read_sources(path)
        rows.update({r["id"]: r for r in new_rows})
        write_sources(path, rows)


def pdf_to_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    pages = [f"[page {i}]\n{page.extract_text() or ''}" for i, page in enumerate(reader.pages, start=1)]
    return "\n\n".join(pages).strip() + "\n"


def collect_url(
    source_id: str,
    url: str,
    doc_type: str,
    title: str,
    company: str = "",
    publisher: str = "",
    published: str = "",
) -> str:
    """Fetch a web page or PDF, cache its text and register it. Returns the cached path."""
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", source_id):
        raise SystemExit(f"source_id must be kebab-case: {source_id!r}")
    headers = {"User-Agent": "Mozilla/5.0 (compatible; semiconductor-supply-chain research project)"}
    r = httpx.get(url, headers=headers, timeout=60, follow_redirects=True)
    r.raise_for_status()
    is_pdf = "pdf" in r.headers.get("content-type", "") or r.content[:5] == b"%PDF-"
    text = pdf_to_text(r.content) if is_pdf else html_to_text(r.text)
    if len(text.strip()) < 200:
        raise SystemExit(f"{url}: only {len(text.strip())} characters of text; page may need JavaScript or block bots")
    paths.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = paths.CACHE_DIR / f"{source_id}.txt"
    cached.write_text(text)
    register_sources([{
        "id": source_id,
        "url": str(r.url),
        "title": title,
        "publisher": publisher,
        "company": company,
        "doc_type": doc_type,
        "published": published,
        "retrieved": dt.date.today().isoformat(),
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
    }])
    return str(cached)


class Edgar:
    def __init__(self) -> None:
        # SEC requires a contact email in the User-Agent: https://www.sec.gov/os/accessing-edgar-data
        contact = os.environ.get("SCG_SEC_CONTACT")
        if not contact:
            raise SystemExit("Set SCG_SEC_CONTACT to an email address SEC can contact (required by EDGAR).")
        user_agent = f"semiconductor-supply-chain research project {contact}"
        self.client = httpx.Client(headers={"User-Agent": user_agent}, timeout=60, follow_redirects=True)
        self._tickers: dict[str, int] | None = None

    def get(self, url: str) -> httpx.Response:
        time.sleep(0.2)  # SEC fair-access limit is 10 req/s
        r = self.client.get(url)
        r.raise_for_status()
        return r

    def cik(self, ticker: str) -> int:
        if self._tickers is None:
            data = self.get("https://www.sec.gov/files/company_tickers.json").json()
            self._tickers = {v["ticker"].upper(): v["cik_str"] for v in data.values()}
        return self._tickers[ticker.upper()]

    def latest_annual(self, ticker: str, forms: tuple[str, ...]) -> dict:
        cik = self.cik(ticker)
        sub = self.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json").json()
        recent = sub["filings"]["recent"]
        for i, form in enumerate(recent["form"]):
            if form in forms:
                acc = recent["accessionNumber"][i].replace("-", "")
                doc = recent["primaryDocument"][i]
                return {
                    "name": sub["name"],
                    "form": form,
                    "filed": recent["filingDate"][i],
                    "period": recent["reportDate"][i],
                    "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}",
                }
        raise LookupError(f"no {forms} filing for {ticker}")


def collect_sec(targets: Path = paths.SOURCES_DIR / "sec_targets.csv", only: set[str] | None = None) -> list[str]:
    """Fetch filings for each target row (company,ticker,forms). Returns source ids written."""
    paths.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    sources_csv = paths.SOURCES_DIR / "sources.csv"
    sources = read_sources(sources_csv)
    edgar = Edgar()
    written = []
    with targets.open(newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        if only and row["company"] not in only:
            continue
        forms = tuple(row["forms"].split(";"))
        filing = edgar.latest_annual(row["ticker"], forms)
        sid = f"{row['company']}-{filing['form'].lower().replace('-', '')}-{filing['period'][:4]}"
        text = html_to_text(edgar.get(filing["url"]).text)
        (paths.CACHE_DIR / f"{sid}.txt").write_text(text)
        sources[sid] = {
            "id": sid,
            "url": filing["url"],
            "title": f"{filing['name']} {filing['form']} for period ending {filing['period']}",
            "publisher": filing["name"],
            "company": row["company"],
            "doc_type": filing["form"],
            "published": filing["filed"],
            "retrieved": dt.date.today().isoformat(),
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
        }
        written.append(sid)
        print(f"{sid}: {len(text):,} chars from {filing['url']}")
    register_sources([sources[sid] for sid in written], sources_csv)
    return written
