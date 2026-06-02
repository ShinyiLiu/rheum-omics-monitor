#!/usr/bin/env python3
"""Monthly public-data monitor for rheumatology single-cell/spatial omics."""

from __future__ import annotations

import argparse
import datetime as dt
import email.message
import html
import json
import os
import re
import smtplib
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULT_OUT = ROOT / "reports"
DEFAULT_STATE = ROOT / "seen_accessions.json"
DEFAULT_ENV = ROOT / ".env"
NCBI_LAST_REQUEST_AT = 0.0
NCBI_MIN_INTERVAL_SECONDS = 0.45

DISEASE_TERMS = [
    "rheumatoid arthritis", "RA", "systemic lupus erythematosus", "SLE", "lupus",
    "Sjogren", "Sjögren", "systemic sclerosis", "scleroderma", "myositis",
    "dermatomyositis", "polymyositis", "vasculitis", "ANCA", "psoriasis",
    "psoriatic arthritis", "inflammatory bowel disease", "IBD", "Behcet", "Behçet",
    "Still disease", "ankylosing spondylitis", "spondyloarthritis",
]
TECH_TERMS = [
    "single cell", "single-cell", "scRNA-seq", "scrna", "single nucleus", "snRNA-seq",
    "spatial transcriptomics", "spatial transcriptome", "Visium", "MERFISH", "seqFISH",
    "Xenium", "CosMx", "Slide-seq", "Stereo-seq",
]
DISEASE_CATEGORIES = [
    ("RA", ["rheumatoid arthritis", "rheumatoid", "RA"]),
    ("SLE / Lupus nephritis", ["systemic lupus erythematosus", "lupus nephritis", "lupus", "SLE", "LN"]),
    ("Sjögren", ["Sjogren", "Sjögren"]),
    ("Systemic sclerosis", ["systemic sclerosis", "scleroderma"]),
    ("Myositis", ["myositis", "dermatomyositis", "polymyositis", "DMD"]),
    ("Vasculitis", ["vasculitis", "ANCA"]),
    ("Psoriasis / PsA", ["psoriasis", "psoriatic arthritis"]),
    ("IBD-associated disease", ["inflammatory bowel disease", "IBD"]),
    ("Behçet", ["Behcet", "Behçet"]),
    ("Still disease", ["Still disease"]),
    ("Spondyloarthritis", ["ankylosing spondylitis", "spondyloarthritis"]),
]
RUN_ACCESSION_RE = re.compile(r"\b[SED]RR\d+\b|\b[SED]RX\d+\b|\b[SED]RP\d+\b|\bDRR\d+\b|\bDRX\d+\b|\bDRP\d+\b")
STUDY_ACCESSION_RE = re.compile(r"\b(?:PRJ[DEN][A-Z]?\d+|GSE\d+|E-MTAB-\d+|SCP\d+)\b")


@dataclass(frozen=True)
class Record:
    accession: str
    title: str
    source: str
    url: str
    published: str = ""
    organism: str = ""
    technology: str = ""
    disease_hint: str = ""
    summary: str = ""

    def key(self) -> str:
        return f"{self.source}:{self.accession}"


@dataclass(frozen=True)
class Study:
    disease: str
    title: str
    sources: tuple[str, ...]
    accessions: tuple[str, ...]
    links: tuple[str, ...]
    published: str
    organism: str
    technology: str


def http_json(url: str, timeout: int = 45, retries: int = 4) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "codex-rheum-omics-monitor/1.0"})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = resp.read().decode("utf-8", errors="replace")
            return json.loads(payload)
        except urllib.error.HTTPError as exc:
            if exc.code not in {429, 500, 502, 503, 504} or attempt >= retries:
                raise
            retry_after = exc.headers.get("Retry-After")
            delay = float(retry_after) if retry_after and retry_after.isdigit() else min(60.0, 2.0 * (2**attempt))
            time.sleep(delay)
    raise RuntimeError("unreachable retry loop")


def ncbi_wait() -> None:
    global NCBI_LAST_REQUEST_AT
    elapsed = time.monotonic() - NCBI_LAST_REQUEST_AT
    if elapsed < NCBI_MIN_INTERVAL_SECONDS:
        time.sleep(NCBI_MIN_INTERVAL_SECONDS - elapsed)
    NCBI_LAST_REQUEST_AT = time.monotonic()


def add_ncbi_identity(params: dict[str, str]) -> dict[str, str]:
    enriched = dict(params)
    for env_name, param_name in [("NCBI_TOOL", "tool"), ("NCBI_EMAIL", "email"), ("NCBI_API_KEY", "api_key")]:
        value = os.environ.get(env_name)
        if value:
            enriched[param_name] = value
    enriched.setdefault("tool", "rheum_omics_monitor")
    return enriched


def load_env_file(path: Path = DEFAULT_ENV) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def contains_any(text: str, terms: list[str]) -> str:
    folded = text.casefold()
    for term in terms:
        if term.casefold() in folded:
            return term
    return ""


def term_matches(text: str, term: str) -> bool:
    if len(term) <= 3 or term.isupper():
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", text) is not None
    return term.casefold() in text.casefold()


def classify_disease(text: str) -> tuple[str, str]:
    for category, terms in DISEASE_CATEGORIES:
        for term in terms:
            if term_matches(text, term):
                return category, term
    return "Other rheumatic/immune", ""


def infer_technology(text: str) -> str:
    if contains_any(text, ["spatial", "visium", "merfish", "seqfish", "xenium", "cosmx", "slide-seq", "stereo-seq"]):
        return "spatial transcriptomics"
    if contains_any(text, ["single cell", "single-cell", "scrna", "snrna", "single nucleus"]):
        return "single-cell transcriptomics"
    return ""


def keep_record(title: str, summary: str = "") -> tuple[bool, str, str]:
    text = f"{title}\n{summary}"
    disease, disease_term = classify_disease(text)
    tech = infer_technology(text)
    return bool(disease_term and tech), disease, tech


def clean_title(title: str, fallback: str) -> str:
    title = " ".join(html.unescape(title or "").split())
    return title or fallback


def extract_accession(candidate: str, fallback: str) -> str:
    text = candidate or ""
    study_match = STUDY_ACCESSION_RE.search(text)
    if study_match:
        return study_match.group(0)
    run_matches = RUN_ACCESSION_RE.findall(text)
    if run_matches:
        unique = sorted(set(run_matches))
        return ", ".join(unique[:8]) + (" ..." if len(unique) > 8 else "")
    return fallback


def normalize_study_title(title: str) -> str:
    folded = re.sub(r"[^a-z0-9]+", " ", title.casefold()).strip()
    folded = re.sub(r"\b(?:single cell|single nucleus|scrna seq|snrna seq|rna seq|dataset|data)\b", " ", folded)
    return re.sub(r"\s+", " ", folded).strip() or title.casefold()


def is_accession_title(title: str) -> bool:
    tokens = re.findall(r"\b[A-Z]{2,4}\d+\b", title)
    clean = re.sub(r"\b[A-Z]{2,4}\d+\b|[,.;\s]|\.\.\.", "", title)
    return bool(tokens) and not clean


def accession_batch_key(accession: str) -> str:
    matches = RUN_ACCESSION_RE.findall(accession)
    if not matches:
        return accession
    first = sorted(set(matches))[0]
    prefix = re.match(r"([A-Z]+)(\d+)", first)
    if not prefix:
        return first
    letters, digits = prefix.groups()
    return f"{letters}{digits[:3]}"


def accession_range_label(accessions: tuple[str, ...]) -> str:
    runs: list[str] = []
    for accession in accessions:
        runs.extend(RUN_ACCESSION_RE.findall(accession))
    unique_runs = sorted(set(runs))
    if len(unique_runs) >= 2:
        return f"SRA run batch {unique_runs[0]}-{unique_runs[-1]} ({len(unique_runs)} runs)"
    if unique_runs:
        return unique_runs[0]
    return "; ".join(accessions)


def ncbi_search(db: str, term: str, since_days: int, retmax: int) -> list[str]:
    params = add_ncbi_identity({
        "db": db,
        "term": term,
        "retmode": "json",
        "retmax": str(retmax),
        "sort": "pub date",
        "datetype": "pdat",
        "reldate": str(since_days),
    })
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + urllib.parse.urlencode(params)
    ncbi_wait()
    data = http_json(url)
    return data.get("esearchresult", {}).get("idlist", [])


def ncbi_summary(db: str, ids: list[str]) -> dict[str, Any]:
    if not ids:
        return {}
    params = add_ncbi_identity({"db": db, "id": ",".join(ids), "retmode": "json"})
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?" + urllib.parse.urlencode(params)
    ncbi_wait()
    return http_json(url).get("result", {})


def fetch_ncbi_geo(since_days: int, retmax: int) -> list[Record]:
    term = "(" + " OR ".join(f'"{t}"' for t in DISEASE_TERMS) + ") AND (" + " OR ".join(f'"{t}"' for t in TECH_TERMS) + ")"
    summaries = ncbi_summary("gds", ncbi_search("gds", term, since_days, retmax))
    records: list[Record] = []
    for uid in summaries.get("uids", []):
        item = summaries.get(uid, {})
        title = item.get("title") or item.get("summary") or ""
        summary = item.get("summary", "")
        keep, disease, tech = keep_record(title, summary)
        if not keep:
            continue
        accession = item.get("accession") or item.get("gse") or uid
        records.append(Record(str(accession), clean_title(title, str(accession)), "NCBI GEO", f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={urllib.parse.quote(str(accession))}", item.get("PDAT", "") or item.get("pdat", ""), item.get("taxon", ""), tech, disease, summary.strip()))
    return records


def fetch_ncbi_sra(since_days: int, retmax: int) -> list[Record]:
    term = "(" + " OR ".join(f'"{t}"' for t in DISEASE_TERMS) + ") AND (" + " OR ".join(f'"{t}"' for t in TECH_TERMS) + ")"
    summaries = ncbi_summary("sra", ncbi_search("sra", term, since_days, retmax))
    records: list[Record] = []
    for uid in summaries.get("uids", []):
        item = summaries.get(uid, {})
        title = item.get("title", "")
        summary = item.get("expxml", "")
        keep, disease, tech = keep_record(title, summary)
        if not keep:
            continue
        accession = extract_accession(item.get("accession") or item.get("runs", "") or item.get("expxml", ""), uid)
        records.append(Record(accession, clean_title(title, str(accession)), "NCBI SRA", f"https://www.ncbi.nlm.nih.gov/sra/?term={urllib.parse.quote(str(accession).split(',', 1)[0])}", item.get("publishdate", ""), item.get("organism", ""), tech, disease, "SRA run/study matched rheumatology and single-cell/spatial keywords."))
    return records


def fetch_cxg(retmax: int) -> list[Record]:
    data = http_json("https://api.cellxgene.cziscience.com/curation/v1/datasets")
    datasets = data.get("datasets", []) if isinstance(data, dict) else data
    records: list[Record] = []
    for item in datasets[: max(retmax, 1)]:
        if not isinstance(item, dict):
            continue
        title = item.get("title", "")
        summary = item.get("description", "")
        keep, disease, tech = keep_record(title, summary)
        if not keep:
            continue
        accession = item.get("dataset_id") or item.get("id") or title
        organism = ", ".join([o.get("label", "") for o in item.get("organism", []) if isinstance(o, dict)])
        records.append(Record(str(accession), clean_title(title, str(accession)), "CELLxGENE", f"https://cellxgene.cziscience.com/e/{accession}.cxg/", item.get("published_at", "") or item.get("created_at", ""), organism, tech, disease, summary.strip()))
    return records


def fetch_ena(since_days: int, retmax: int) -> list[Record]:
    since = (dt.date.today() - dt.timedelta(days=since_days)).isoformat()
    params = {
        "result": "study",
        "query": f'first_public>="{since}"',
        "fields": "study_accession,secondary_study_accession,study_title,study_description,first_public,scientific_name",
        "format": "json",
        "limit": str(retmax),
    }
    data = http_json("https://www.ebi.ac.uk/ena/portal/api/search?" + urllib.parse.urlencode(params))
    records: list[Record] = []
    for item in data:
        title = item.get("study_title", "")
        summary = item.get("study_description", "")
        keep, disease, tech = keep_record(title, summary)
        if not keep:
            continue
        accession = item.get("study_accession") or item.get("secondary_study_accession") or title
        records.append(Record(str(accession), clean_title(title, str(accession)), "ENA", f"https://www.ebi.ac.uk/ena/browser/view/{urllib.parse.quote(str(accession))}", item.get("first_public", ""), item.get("scientific_name", ""), tech, disease, summary.strip()))
    return records


def collect_records(since_days: int, retmax: int) -> tuple[list[Record], list[str]]:
    sources = [
        ("NCBI GEO", lambda: fetch_ncbi_geo(since_days, retmax)),
        ("NCBI SRA", lambda: fetch_ncbi_sra(since_days, retmax)),
        ("ENA", lambda: fetch_ena(since_days, retmax)),
        ("CELLxGENE", lambda: fetch_cxg(retmax)),
    ]
    records: list[Record] = []
    warnings: list[str] = []
    for name, fetcher in sources:
        try:
            records.extend(fetcher())
            time.sleep(0.6)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            if isinstance(exc, urllib.error.HTTPError) and exc.code == 429:
                warnings.append(f"{name}: NCBI/remote service rate-limited this run after retries; this source was skipped temporarily")
            else:
                warnings.append(f"{name}: {exc}")
    dedup: dict[str, Record] = {}
    for rec in records:
        dedup.setdefault(rec.key(), rec)
    return sorted(dedup.values(), key=lambda r: (r.published, r.source, r.accession), reverse=True), warnings


def build_studies(records: list[Record]) -> list[Study]:
    grouped: dict[tuple[str, str], list[Record]] = {}
    for rec in records:
        disease, _ = classify_disease(f"{rec.title}\n{rec.summary}\n{rec.disease_hint}")
        if rec.source == "NCBI SRA" and is_accession_title(rec.title):
            group_key = (disease, f"sra-run-batch:{accession_batch_key(rec.accession)}")
        else:
            group_key = (disease, normalize_study_title(rec.title))
        grouped.setdefault(group_key, []).append(rec)

    studies: list[Study] = []
    for (disease, _), group in grouped.items():
        accessions = sorted({rec.accession for rec in group if rec.accession})
        title_candidates = [rec.title for rec in group if not is_accession_title(rec.title)]
        title = max(title_candidates, key=len) if title_candidates else accession_range_label(tuple(accessions))
        studies.append(Study(
            disease=disease,
            title=title,
            sources=tuple(sorted({rec.source for rec in group if rec.source})),
            accessions=tuple(accessions),
            links=tuple(sorted({rec.url for rec in group if rec.url})),
            published=sorted({rec.published for rec in group if rec.published}, reverse=True)[0] if any(rec.published for rec in group) else "",
            organism=", ".join(sorted({rec.organism for rec in group if rec.organism})),
            technology=", ".join(sorted({rec.technology for rec in group if rec.technology})),
        ))
    disease_order = {name: index for index, (name, _) in enumerate(DISEASE_CATEGORIES)}
    return sorted(studies, key=lambda s: (disease_order.get(s.disease, 999), s.title.casefold(), s.published))


def load_seen(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    return set(data.get("seen", []))


def save_seen(path: Path, keys: set[str]) -> None:
    path.write_text(json.dumps({"updated_at": dt.datetime.now().isoformat(timespec="seconds"), "seen": sorted(keys)}, ensure_ascii=False, indent=2), encoding="utf-8")


def render_markdown(records: list[Record], warnings: list[str], since_days: int, only_new: bool) -> str:
    today = dt.date.today().isoformat()
    label = "新增候选数据集" if only_new else "候选数据集"
    studies = build_studies(records)
    lines = [
        f"# 风湿免疫单细胞/空间转录组公共数据报告 - {today}",
        "",
        f"- 检索窗口：最近 {since_days} 天",
        "- 匹配范围：风湿免疫疾病 + single-cell/snRNA-seq/spatial transcriptomics 关键词",
        f"- {label}：{len(studies)} 个研究 / {len(records)} 条数据库记录",
        "",
    ]
    if not studies:
        lines.extend(["本次未发现新的高置信候选数据集。", ""])
    current_disease = ""
    index_by_disease: dict[str, int] = {}
    for study in studies:
        if study.disease != current_disease:
            current_disease = study.disease
            index_by_disease[current_disease] = 0
            lines.extend([f"## {current_disease}", ""])
        index_by_disease[current_disease] += 1
        lines.extend([
            f"### {index_by_disease[current_disease]}. {study.title}",
            f"- 数据库：{', '.join(study.sources)}",
            f"- Accession：{'; '.join(study.accessions) if study.accessions else '未提供'}",
            f"- 疾病：{study.disease}",
            f"- 发布时间：{study.published or '未提供'}",
            f"- 物种：{study.organism or '未提供'}",
            f"- 技术类型：{study.technology or '未判定'}",
        ])
        if study.links:
            links = "；".join(study.links[:3])
            if len(study.links) > 3:
                links += f"；另有 {len(study.links) - 3} 个链接"
            lines.append(f"- 链接：{links}")
        lines.append("")
    if warnings:
        lines.extend(["## 检索警告", ""])
        lines.extend(f"- {warning}" for warning in warnings)
        lines.append("")
    return "\n".join(lines)


def send_email(subject: str, body: str) -> None:
    host = os.environ.get("SMTP_HOST", "smtp.qq.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    user = os.environ.get("SMTP_USER", "")
    auth_code = os.environ.get("SMTP_AUTH_CODE", "")
    recipient = os.environ.get("REPORT_TO_EMAIL", user)
    if not user or not auth_code or not recipient:
        raise RuntimeError("Missing SMTP_USER, SMTP_AUTH_CODE, or REPORT_TO_EMAIL environment variable.")

    msg = email.message.EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = recipient
    msg.set_content(body)

    with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=60) as smtp:
        smtp.login(user, auth_code)
        smtp.send_message(msg)


def main(argv: list[str]) -> int:
    load_env_file()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since-days", type=int, default=35, help="Lookback window for public records.")
    parser.add_argument("--retmax", type=int, default=80, help="Maximum records to ask from each source.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--send-email", action="store_true", help="Send report through SMTP.")
    parser.add_argument("--test-email", action="store_true", help="Send a short SMTP test email and exit.")
    parser.add_argument("--include-seen", action="store_true", help="Report all matches instead of only first-seen records.")
    args = parser.parse_args(argv)

    if args.test_email:
        send_email("风湿免疫单细胞/空间转录组监控：SMTP 测试", "这是一封测试邮件。收到此邮件说明 SMTP 配置可用。")
        print("test_email=sent")
        return 0

    args.out_dir.mkdir(parents=True, exist_ok=True)
    records, warnings = collect_records(args.since_days, args.retmax)
    seen = load_seen(args.state_file)
    selected = records if args.include_seen else [rec for rec in records if rec.key() not in seen]

    now = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = args.out_dir / f"rheum_sc_spatial_report_{now}.md"
    json_path = args.out_dir / f"rheum_sc_spatial_records_{now}.json"
    report = render_markdown(selected, warnings, args.since_days, only_new=not args.include_seen)
    report_path.write_text(report, encoding="utf-8")
    json_path.write_text(json.dumps([rec.__dict__ for rec in selected], ensure_ascii=False, indent=2), encoding="utf-8")

    save_seen(args.state_file, seen | {rec.key() for rec in records})
    if args.send_email:
        subject = f"风湿免疫单细胞/空间转录组公共数据报告：{len(build_studies(selected))} 个研究候选"
        send_email(subject, report)

    print(f"records_found={len(records)}")
    print(f"records_reported={len(selected)}")
    print(f"report={report_path}")
    print(f"json={json_path}")
    if warnings:
        print("warnings=" + " | ".join(warnings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
