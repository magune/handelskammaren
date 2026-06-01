"""
fullrun.py — Run document pairs through an LLM (model set by the MODEL constant) via Batch API.

The model/version is version-agnostic in the filenames; change the single MODEL
constant (e.g. "gpt-5.5" → "gpt-5.6") and it is printed to the console at startup.

v2 input model: each pair is one CERTIFICATE supplied as structured JSON
(Testdata/v2 JSON files/origin_json) + one or more INVOICE PDFs. The certificate
JSON is matched to an existing test pair by the certificate id (SEG-...) printed
inside the old certificate PDF, which supplies the invoice PDF(s) and the
MATCH/MISMATCH label.

Modes:
  FAIL_FAST = False  →  Full run of all pairs
  FAIL_FAST = True   →  Regression guard, stops on first FAIL

Set ONLY_PAIRS to a list of pair IDs to run a subset, or None for all pairs.

Results saved to: FullrunResults/
State file:       fullrun_state.json  (resume-safe)
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
import time
from pathlib import Path

import fitz  # PyMuPDF — extract certificate id from certificate PDFs

from dotenv import load_dotenv
from openai import OpenAI, APIConnectionError, APITimeoutError

load_dotenv()

BASE_DIR        = Path(__file__).parent
TESTSYSTEM_DIR  = BASE_DIR / "Testdata" / "Testsystem företag"
MULTI_INV_DIR   = BASE_DIR / "Testdata" / "Testsystem med flera fakturor"
RESULTS_DIR     = BASE_DIR / "FullrunResults"
BASELINE_DIR    = BASE_DIR / "FullrunResults"   # own previous run — prompt-iteration regression detection
# (v1↔v2 comparison is done separately by diffing FullrunResults/ against V1_baseline_gpt54/)
PROMPT_FILE     = BASE_DIR / "api_prompt.md"
SCHEMA_FILE     = BASE_DIR / "schema_slim_strict.json"
STATE_FILE      = BASE_DIR / "fullrun_state.json"

# v2: certificates supplied as structured JSON
ORIGIN_JSON_DIR = BASE_DIR / "Testdata" / "v2 JSON files" / "origin_json"
CERT_ID_CACHE   = BASE_DIR / "v2_cert_id_cache.json"  # cert PDF path -> SEG id

RESULTS_DIR.mkdir(exist_ok=True)

MODEL            = "gpt-5.4"   # A/B visade 5.4/medium bäst på de svåra paren OCH billigast
REASONING_EFFORT = "medium"
# gpt-5.4 Batch API pricing (50% off standard $3.75 / $0.375 cached / $15.00). Cost-reporting only.
# Sync mode pays 2x these (standard rate); the sync path multiplies by 2.
INPUT_PRICE        = 1.875  # $/1M fresh input tokens   (Batch = 50% off $3.75)
CACHED_INPUT_PRICE = 0.1875 # $/1M cached input tokens  (Batch = 50% off $0.375)
OUTPUT_PRICE       = 7.50   # $/1M output tokens        (Batch = 50% off $15.00)
COST_LIMIT_USD   = 60.0
POLL_INTERVAL    = 30

# ---------------------------------------------------------------------------
# Mode settings
# ---------------------------------------------------------------------------
# SYNC_MODE: run synchronously (immediate responses) instead of the Batch API.
# Use for smoke tests / fast iteration — no 24h batch window. NOTE: synchronous
# calls are NOT discounted, so they cost 2x the Batch rate (reported accordingly).
# False = Batch API (50% cheaper, but up to 24h completion window).
SYNC_MODE        = False

# FAIL_FAST: stop at first FAIL result (regression guard mode). Batch mode only.
FAIL_FAST        = False

# Chunk size: smaller = faster FAIL_FAST reaction, larger = fewer API calls
# Recommended: 2 for FAIL_FAST, 20-50 for full runs
CHUNK_SIZE       = 50

# Filter to specific pairs, or None for all.
# Example: ["P001", "P003", "P031"]
ONLY_PAIRS       = None   # full run — all 182 v2 pairs (establish baseline)

# SAMPLE_N: run a deterministic, stratified sample of N pairs (balanced MATCH/MISMATCH
# + guaranteed multi-invoice), for cheap iteration. None = all pairs (full baseline).
SAMPLE_N         = None

# Max retries per pair when LLM returns unparseable/garbage JSON
MAX_GARBAGE_RETRIES = 2

# ---------------------------------------------------------------------------

client        = OpenAI(timeout=300.0, max_retries=2)  # fail fast on stalls; allow long reasoning calls
system_prompt = PROMPT_FILE.read_text(encoding="utf-8")
prompt_hash   = hashlib.sha256(system_prompt.encode()).hexdigest()[:12]
schema        = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def api_call(func, *args, **kwargs):
    delay = 15
    attempt = 0
    while True:
        try:
            return func(*args, **kwargs)
        except (APIConnectionError, APITimeoutError) as e:
            attempt += 1
            print(f"  [network error #{attempt}] {e} — retrying in {delay}s...", flush=True)
            time.sleep(delay)
            delay = min(delay * 2, 300)
        except Exception:
            raise


def cost_usd(input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> float:
    """Batch-basis cost. Cached input tokens are billed at the discounted cached rate."""
    fresh_in = max(0, input_tokens - cached_tokens)
    return (fresh_in * INPUT_PRICE + cached_tokens * CACHED_INPUT_PRICE + output_tokens * OUTPUT_PRICE) / 1_000_000


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return None


# ---------------------------------------------------------------------------
# Baseline comparison
# ---------------------------------------------------------------------------

def load_baseline() -> dict[str, dict]:
    """Load previous results as baseline for regression detection."""
    baseline = {}
    if not BASELINE_DIR.exists():
        return baseline
    for f in BASELINE_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            meta = data.get("_meta", {})
            pair_name = meta.get("pair", "")
            if pair_name:
                baseline[pair_name] = {
                    "status": meta.get("status", ""),
                    "actual": meta.get("actual", ""),
                    "prompt_hash": meta.get("prompt_hash", ""),
                }
        except Exception:
            pass
    return baseline


def check_regression(pair_name: str, new_status: str, _new_actual: str, baseline: dict) -> str:
    """Compare against baseline. Returns label string or empty."""
    prev = baseline.get(pair_name)
    if not prev or prev.get("prompt_hash") == prompt_hash:
        return ""  # no baseline or same prompt
    prev_status = prev.get("status", "")
    if prev_status == new_status:
        return "(unchanged)"
    if prev_status == "PASS" and new_status in ("FAIL", "REVIEW"):
        return f"⚠️REGRESSION (was {prev.get('actual', '?')})"
    if prev_status in ("FAIL", "REVIEW") and new_status == "PASS":
        return f"✨IMPROVED (was {prev.get('actual', '?')})"
    return f"(changed: {prev_status}→{new_status})"


# ---------------------------------------------------------------------------
# Garbage detection
# ---------------------------------------------------------------------------

def is_garbage(result: dict) -> bool:
    """Check if LLM response is garbage/unparseable."""
    overall = result.get("overall_assessment")
    if not overall:
        return True
    comparison = overall.get("comparison_result", "")
    if comparison not in ("IDENTICAL", "NOT_IDENTICAL", "MANUAL_REVIEW"):
        return True
    confidence = overall.get("confidence")
    if confidence is not None and (confidence < 0 or confidence > 1):
        return True
    return False


# ---------------------------------------------------------------------------
# Pair discovery
# ---------------------------------------------------------------------------

SEG_RE = re.compile(r"SEG[-\s]?(\d{2}[A-Z])[-\s]?(\d{6})")


def _normalize_cert_id(raw: str) -> str | None:
    """Normalize any 'SEG_23D_855559' / 'SEG-23D-855559' / 'SEG 23D 855559' to 'SEG-23D-855559'."""
    m = SEG_RE.search(raw or "")
    return f"SEG-{m.group(1)}-{m.group(2)}" if m else None


def _build_json_index() -> dict[str, Path]:
    """Map normalized CertificateId -> certificate JSON path."""
    index: dict[str, Path] = {}
    for jf in sorted(ORIGIN_JSON_DIR.glob("*.json")):
        cid = None
        try:
            cid = _normalize_cert_id(json.loads(jf.read_text(encoding="utf-8")).get("CertificateId", ""))
        except Exception:
            pass
        cid = cid or _normalize_cert_id(jf.stem)  # fall back to filename
        if cid:
            index[cid] = jf
    return index


def _extract_cert_id_from_pdf(pdf_path: Path) -> str | None:
    """Read the SEG certificate id printed inside a certificate PDF."""
    try:
        doc = fitz.open(pdf_path)
        text = "".join(page.get_text() for page in doc)
        doc.close()
    except Exception:
        return None
    return _normalize_cert_id(text)


def _resolve_cert_id(pdf_path: Path, cache: dict) -> str | None:
    """Resolve a certificate PDF's id, caching by path so PDFs aren't re-parsed every run."""
    key = str(pdf_path)
    if key in cache:
        return cache[key]
    cid = _extract_cert_id_from_pdf(pdf_path)
    cache[key] = cid
    return cid


def discover_pairs() -> list[dict]:
    """Discover v2 test pairs: certificate JSON + invoice PDF(s) + MATCH/MISMATCH label.

    The certificate now comes as structured JSON. Each JSON is matched to an
    existing test pair by the certificate id (SEG-...) printed inside the old
    certificate PDF; that pair supplies the invoice PDF(s) and the label.
    Pairs whose certificate has no matching JSON are excluded from v2.
    """
    json_index = _build_json_index()
    id_cache = {}
    if CERT_ID_CACHE.exists():
        try:
            id_cache = json.loads(CERT_ID_CACHE.read_text(encoding="utf-8"))
        except Exception:
            id_cache = {}
    cache_start = dict(id_cache)
    pairs = []
    used_ids = set()

    # --- Testsystem företag: flat files named P013_MATCH_certificate.pdf ---
    pair_files: dict[str, dict] = {}
    for pdf in sorted(TESTSYSTEM_DIR.glob("*.pdf")):
        parts = pdf.stem.split("_")
        if len(parts) < 3 or parts[1] not in ("MATCH", "MISMATCH") or parts[2] not in ("certificate", "invoice"):
            continue
        key = f"{parts[0]}_{parts[1]}"
        pair_files.setdefault(key, {})[parts[2]] = pdf

    for key in sorted(pair_files):
        docs = pair_files[key]
        if "certificate" not in docs or "invoice" not in docs:
            continue
        cert_id = _resolve_cert_id(docs["certificate"], id_cache)
        cert_json = json_index.get(cert_id) if cert_id else None
        if cert_json is None:
            continue  # no JSON certificate for this pair -> excluded from v2
        used_ids.add(cert_id)
        category = key.split("_")[1]
        pairs.append({
            "name":         key,
            "category":     category,
            "expected":     "IDENTICAL" if category == "MATCH" else "NOT_IDENTICAL",
            "cert_id":      cert_id,
            "cert_json":    str(cert_json),
            "invoice_pdfs": [str(docs["invoice"])],
        })

    # --- Testsystem med flera fakturor: subdirs named MATCH_<id> or MISMATCH_<id> ---
    # Each subdir contains 1 certificate PDF + 1-3 invoice PDFs.
    if MULTI_INV_DIR.exists():
        for subdir in sorted(MULTI_INV_DIR.iterdir()):
            if not subdir.is_dir():
                continue
            parts = subdir.name.split("_", 1)
            if len(parts) != 2 or parts[0] not in ("MATCH", "MISMATCH"):
                continue
            category, cert_id_raw = parts[0], parts[1]
            pdfs = sorted(subdir.glob("*.pdf"))
            # Certificate = PDF whose stem contains the dir's <id> (case-insensitive)
            cert_pdfs = [p for p in pdfs if cert_id_raw.lower() in p.stem.lower()]
            inv_pdfs  = [p for p in pdfs if p not in cert_pdfs]
            if not inv_pdfs:
                print(f"  [warn] {subdir.name}: ingen fakturafil hittad — hoppar över")
                continue
            cert_id = _normalize_cert_id(cert_id_raw)
            if cert_id not in json_index and cert_pdfs:
                cert_id = _resolve_cert_id(cert_pdfs[0], id_cache)  # fall back to PDF text
            cert_json = json_index.get(cert_id) if cert_id else None
            if cert_json is None or cert_id in used_ids:
                continue
            used_ids.add(cert_id)
            key = f"{cert_id_raw}_{category}"
            pairs.append({
                "name":         key,
                "category":     category,
                "expected":     "IDENTICAL" if category == "MATCH" else "NOT_IDENTICAL",
                "cert_id":      cert_id,
                "cert_json":    str(cert_json),
                "invoice_pdfs": [str(p) for p in inv_pdfs],
            })

    if id_cache != cache_start:
        CERT_ID_CACHE.write_text(json.dumps(id_cache, indent=2, ensure_ascii=False), encoding="utf-8")

    unused = set(json_index) - used_ids
    if unused:
        print(f"  [info] {len(unused)} certifikat-JSON saknar matchande testpar (hoppas över).")
    print(f"  [info] {len(pairs)} v2-par (certifikat-JSON + faktura-PDF).")

    return pairs


# ---------------------------------------------------------------------------
# Upload / batch
# ---------------------------------------------------------------------------

def upload_pdfs(paths: list[str]) -> dict[str, str]:
    file_ids = {}
    total = len(paths)
    for i, path_str in enumerate(paths, 1):
        path = Path(path_str)
        size_kb = path.stat().st_size / 1024
        print(f"    [{i}/{total}] uploading {path.name} ({size_kb:.0f} KB)...", flush=True)
        with path.open("rb") as fh:
            uploaded = api_call(
                client.files.create,
                file=(path.name, fh, "application/pdf"),
                purpose="user_data",
            )
        file_ids[path_str] = uploaded.id
    return file_ids


def delete_files(file_ids: dict[str, str]):
    for fid in file_ids.values():
        try:
            client.files.delete(fid)
        except Exception:
            pass


def build_request(pair: dict, file_ids: dict[str, str]) -> dict:
    cert = json.loads(Path(pair["cert_json"]).read_text(encoding="utf-8"))
    user_content = [
        {"type": "file", "file": {"file_id": file_ids[f]}}
        for f in pair["invoice_pdfs"]
    ]
    user_content.append({
        "type": "text",
        "text": "CERTIFICATE OF ORIGIN (structured JSON):\n"
                + json.dumps(cert, ensure_ascii=False, indent=2),
    })
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_content},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name":   "verification_output",
                "strict": True,
                "schema": schema,
            },
        },
        "max_completion_tokens": 16000,
    }
    if REASONING_EFFORT:
        body["reasoning_effort"] = REASONING_EFFORT
    return {
        "custom_id": pair["name"],
        "method":    "POST",
        "url":       "/v1/chat/completions",
        "body":      body,
    }


def submit_chunk(chunk: list[dict], chunk_idx: int) -> dict:
    all_paths = list({f for p in chunk for f in p["invoice_pdfs"]})
    print(f"  [chunk {chunk_idx+1}] Uploading {len(all_paths)} invoice PDFs...", flush=True)
    file_ids = upload_pdfs(all_paths)

    lines = [json.dumps(build_request(p, file_ids), ensure_ascii=False) for p in chunk]
    jsonl_bytes = "\n".join(lines).encode("utf-8")
    print(f"  [chunk {chunk_idx+1}] Submitting batch ({len(jsonl_bytes)/1024:.1f} KB, {len(chunk)} pairs)...", flush=True)

    uploaded = api_call(
        client.files.create,
        file=("batch_input.jsonl", jsonl_bytes, "application/jsonl"),
        purpose="batch",
    )
    batch = api_call(
        client.batches.create,
        input_file_id=uploaded.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
    )
    print(f"  [chunk {chunk_idx+1}] Batch submitted: {batch.id}", flush=True)
    return {
        "chunk_idx":  chunk_idx,
        "batch_id":   batch.id,
        "pair_names": [p["name"] for p in chunk],
        "file_ids":   file_ids,
        "done":       False,
    }


# ---------------------------------------------------------------------------
# Result collection
# ---------------------------------------------------------------------------

def process_result(custom_id: str, pair: dict, result: dict, tok_in: int, tok_out: int, baseline: dict, cached_in: int = 0) -> dict:
    """Score one verification result, print a line, write the result file, and return its summary."""
    overall           = result.get("overall_assessment") or {}
    comparison_result = overall.get("comparison_result") or "PARSE_ERROR"
    # Facit (pair["expected"]) är ALLTID IDENTICAL eller NOT_IDENTICAL.
    # Systemets output kan vara IDENTICAL, NOT_IDENTICAL eller MANUAL_REVIEW.
    # MANUAL_REVIEW är ett ACCEPTABELT svar — det räknas ALDRIG som FAIL, men är inte heller
    # en MATCH (PASS). Det är en egen kategori (REVIEW).
    if comparison_result == "MANUAL_REVIEW":
        status = "REVIEW"
    elif comparison_result == pair["expected"]:
        status = "PASS"
    else:
        status = "FAIL"
    conf              = overall.get("confidence", "?")

    reg_label = check_regression(custom_id, status, comparison_result, baseline)
    status_icon = "✓" if status == "PASS" else ("?" if status == "REVIEW" else "✗")
    cache_note = f"cached={cached_in:,}/{tok_in:,}" if tok_in else ""
    print(f"    {status_icon} {custom_id:35s} {status:6s}  got={str(comparison_result):14s}  conf={conf}  in={tok_in:,} {cache_note} out={tok_out:,}  {reg_label}", flush=True)

    result["_meta"] = {
        "tested_at":   datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "prompt_hash": prompt_hash,
        "model":       MODEL,
        "tier":        2,
        "pair":        custom_id,
        "expected":    pair["expected"],
        "actual":      comparison_result,
        "status":      status,
    }
    out_path = RESULTS_DIR / f"{custom_id}_{pair['category']}.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "name":          custom_id,
        "category":      pair["category"],
        "expected":      pair["expected"],
        "actual":        comparison_result,
        "status":        status,
        "confidence":    conf,
        "input_tokens":  tok_in,
        "cached_tokens": cached_in,
        "output_tokens": tok_out,
    }


def run_sync(pairs: list[dict], baseline: dict) -> list[dict]:
    """Synchronous (non-batch) run — immediate responses, no 24h batch window.

    Uploads each invoice PDF once, then calls the chat completions API per pair.
    NOT discounted: synchronous calls cost ~2x the Batch rate.
    """
    all_paths = list({f for p in pairs for f in p["invoice_pdfs"]})
    print(f"  Uploading {len(all_paths)} invoice PDFs...", flush=True)
    file_ids = upload_pdfs(all_paths)
    results: list[dict] = []
    try:
        for pair in pairs:
            body = build_request(pair, file_ids)["body"]
            try:
                resp = api_call(client.chat.completions.create, **body)
            except Exception as e:
                print(f"    ✗ {pair['name']:35s} API error: {e}", flush=True)
                results.append({"name": pair["name"], "error": str(e)})
                continue
            content = resp.choices[0].message.content
            try:
                result = json.loads(content)
            except json.JSONDecodeError as e:
                print(f"  [json error] {pair['name']}: {e}", flush=True)
                results.append({"name": pair["name"], "error": f"json: {e}"})
                continue
            if is_garbage(result):
                print(f"  [garbage] {pair['name']}: invalid response structure", flush=True)
                results.append({"name": pair["name"], "error": "garbage"})
                continue
            usage   = resp.usage
            tok_in  = getattr(usage, "prompt_tokens", 0) or 0
            tok_out = getattr(usage, "completion_tokens", 0) or 0
            details = getattr(usage, "prompt_tokens_details", None)
            cached  = (getattr(details, "cached_tokens", 0) if details else 0) or 0
            results.append(process_result(pair["name"], pair, result, tok_in, tok_out, baseline, cached))
    finally:
        delete_files(file_ids)
    return results


def collect_chunk(batch_obj, chunk_state: dict, pair_by_name: dict, baseline: dict) -> tuple[list[dict], list[dict]]:
    """Collect results. Returns (results, garbage_pairs) where garbage_pairs need retry."""
    if not getattr(batch_obj, "output_file_id", None):
        print(f"  [chunk {chunk_state['chunk_idx']+1}] No output — batch failed.", flush=True)
        return [], []

    output_text = api_call(client.files.content, batch_obj.output_file_id).text
    results = []
    garbage_pairs = []

    for line in output_text.strip().splitlines():
        entry     = json.loads(line)
        custom_id = entry["custom_id"]
        pair      = pair_by_name.get(custom_id)
        if pair is None:
            continue
        error = entry.get("error")
        body  = entry.get("response", {}).get("body", {})
        if error or not body:
            results.append({"name": custom_id, "error": str(error)})
            continue
        message = body["choices"][0]["message"]
        try:
            result = json.loads(message["content"])
        except json.JSONDecodeError as e:
            print(f"  [json error] {custom_id}: {e}", flush=True)
            garbage_pairs.append(pair)
            continue

        # Check for garbage response
        if is_garbage(result):
            print(f"  [garbage] {custom_id}: invalid response structure", flush=True)
            garbage_pairs.append(pair)
            continue

        usage   = body.get("usage", {})
        tok_in  = usage.get("prompt_tokens", 0)
        tok_out = usage.get("completion_tokens", 0)
        cached  = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
        results.append(process_result(custom_id, pair, result, tok_in, tok_out, baseline, cached))

    return results, garbage_pairs


# ---------------------------------------------------------------------------
# Progress / summary
# ---------------------------------------------------------------------------

def print_progress(all_results: list[dict], total: int, cumulative_cost: float):
    done    = len(all_results)
    if done == 0:
        return
    correct = sum(1 for r in all_results if r.get("status") == "PASS")
    review  = sum(1 for r in all_results if r.get("status") == "REVIEW")
    fail    = sum(1 for r in all_results if r.get("status") == "FAIL" or "error" in r)
    print(f"\n  ┌─ PROGRESS ({'='*38})")
    print(f"  │  Done:    {done}/{total}  ({done/total*100:.0f}%)")
    print(f"  │  PASS:    {correct}  ({correct/done*100:.1f}%)")
    print(f"  │  REVIEW:  {review}  ({review/done*100:.1f}%)")
    print(f"  │  FAIL:    {fail}  ({fail/done*100:.1f}%)")
    print(f"  │  Cost so far: ${cumulative_cost:.4f} USD  (limit: ${COST_LIMIT_USD})")
    print(f"  └{'─'*48}", flush=True)


def print_summary(all_results: list[dict], cumulative_cost: float, baseline: dict):
    total   = len(all_results)
    if total == 0:
        print("No results.")
        return
    correct = sum(1 for r in all_results if r.get("status") == "PASS")
    review  = sum(1 for r in all_results if r.get("status") == "REVIEW")
    fail    = sum(1 for r in all_results if r.get("status") == "FAIL" or "error" in r)

    # Count regressions and improvements
    regressions = []
    improvements = []
    for r in all_results:
        prev = baseline.get(r["name"])
        if not prev or prev.get("prompt_hash") == prompt_hash:
            continue
        prev_status = prev.get("status", "")
        if prev_status == "PASS" and r.get("status") in ("FAIL", "REVIEW"):
            regressions.append(r)
        elif prev_status in ("FAIL", "REVIEW") and r.get("status") == "PASS":
            improvements.append(r)

    total_in     = sum(r.get("input_tokens", 0) for r in all_results)
    total_cached = sum(r.get("cached_tokens", 0) for r in all_results)
    total_out    = sum(r.get("output_tokens", 0) for r in all_results)

    print(f"\n{'='*70}")
    print(f"  FINAL RESULTS — {MODEL} — {total} pairs")
    print(f"  Prompt hash: {prompt_hash}")
    print(f"  {'─'*66}")
    print(f"  PASS:   {correct:4d}  ({correct/total*100:.1f}%)")
    print(f"  REVIEW: {review:4d}  ({review/total*100:.1f}%)")
    print(f"  FAIL:   {fail:4d}  ({fail/total*100:.1f}%)")
    print(f"  {'─'*66}")

    if regressions:
        print(f"\n  ⚠️  REGRESSIONS: {len(regressions)}")
        for r in regressions:
            prev = baseline[r["name"]]
            print(f"    ⚠️  {r['name']:30s}  {prev['status']}→{r['status']}  (was {prev.get('actual','?')} → {r.get('actual','?')})")

    if improvements:
        print(f"\n  ✨ IMPROVEMENTS: {len(improvements)}")
        for r in improvements:
            prev = baseline[r["name"]]
            print(f"    ✨ {r['name']:30s}  {prev['status']}→{r['status']}  (was {prev.get('actual','?')} → {r.get('actual','?')})")

    if fail > 0:
        print(f"\n  FAILURES:")
        for r in all_results:
            if r.get("status") == "FAIL":
                print(f"    FAIL  {r['name']:30s}  expected={r['expected']:16s}  got={r.get('actual','?'):16s}  conf={r.get('confidence','?')}")

    if review > 0:
        print(f"\n  MANUAL REVIEW:")
        for r in all_results:
            if r.get("status") == "REVIEW":
                print(f"    REVIEW  {r['name']:30s}  expected={r['expected']}")

    cache_pct = (total_cached / total_in * 100) if total_in else 0
    print(f"\n  TOKENS & COST:")
    print(f"    Input tokens:       {total_in:,}  (of which cached: {total_cached:,} = {cache_pct:.0f}%)")
    print(f"    Output tokens:      {total_out:,}")
    print(f"    Total cost:         ${cumulative_cost:.4f}  ({'SYNC/standard rate' if SYNC_MODE else 'Batch rate'})")
    if total > 0:
        print(f"    Avg cost per pair:  ${cumulative_cost/total:.4f}")
    print(f"{'='*70}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def stratified_sample(pairs: list[dict], n: int) -> list[dict]:
    """Deterministic, stratified sample of n pairs: balanced MATCH/MISMATCH, spread
    across the sorted set (stride), with >=2 multi-invoice pairs guaranteed."""
    if not n or n >= len(pairs):
        return pairs
    by_name = lambda L: sorted(L, key=lambda p: p["name"])
    matches = by_name([p for p in pairs if p["category"] == "MATCH"])
    misses  = by_name([p for p in pairs if p["category"] == "MISMATCH"])

    def stride(items: list[dict], k: int) -> list[dict]:
        if k <= 0 or not items:
            return []
        if k >= len(items):
            return list(items)
        step = len(items) / k
        return [items[min(len(items) - 1, int(i * step))] for i in range(k)]

    n_match = n // 2
    chosen = {p["name"]: p for p in stride(matches, n_match)}
    for p in stride(misses, n - n_match):
        chosen[p["name"]] = p

    # Guarantee >=2 multi-invoice pairs (swap out single-invoice picks if needed).
    multi = by_name([p for p in pairs if len(p["invoice_pdfs"]) > 1])
    need = 2 - sum(1 for p in chosen.values() if len(p["invoice_pdfs"]) > 1)
    singles = sorted([nm for nm, p in chosen.items() if len(p["invoice_pdfs"]) == 1])
    for mp in multi:
        if need <= 0:
            break
        if mp["name"] in chosen:
            continue
        if singles:
            del chosen[singles.pop()]
        chosen[mp["name"]] = mp
        need -= 1

    return by_name(list(chosen.values()))


def main():
    pairs = discover_pairs()
    if not pairs:
        print("No pairs found.")
        return

    # Filter pairs if ONLY_PAIRS is set
    if ONLY_PAIRS is not None:
        pairs = [p for p in pairs if p["name"].split("_")[0] in ONLY_PAIRS or p["name"] in ONLY_PAIRS]
        if not pairs:
            print(f"No pairs matched filter: {ONLY_PAIRS}")
            return

    # Deterministic stratified sample (cheap iteration); SAMPLE_N=None for full set
    if SAMPLE_N is not None:
        pairs = stratified_sample(pairs, SAMPLE_N)
        print(f"  [sample] running stratified subset of {len(pairs)} pairs (SAMPLE_N={SAMPLE_N})")

    pair_by_name = {p["name"]: p for p in pairs}

    # Load baseline for regression detection and back up if prompt changed
    baseline = load_baseline()
    baseline_count = sum(1 for b in baseline.values() if b.get("prompt_hash") != prompt_hash)

    if baseline_count > 0:
        backup_dir = BASE_DIR / "FullrunResults_baseline"
        if not backup_dir.exists():
            import shutil
            shutil.copytree(RESULTS_DIR, backup_dir)
            print(f"  Baseline backed up to {backup_dir.name}/ ({baseline_count} results)")

    if SYNC_MODE:
        print(f"fullrun [model {MODEL}] — SYNC mode (non-batch, immediate responses)")
        print(f"  model={MODEL}  effort={REASONING_EFFORT}  prompt={PROMPT_FILE.name}  hash={prompt_hash}")
        print(f"  {len(pairs)} pairs  |  Results → {RESULTS_DIR.name}/")
        if baseline_count > 0:
            print(f"  Baseline: {baseline_count} pairs (regression detection active)")
        print()
        results = run_sync(pairs, baseline)
        # Synchronous = standard rate = 2x the Batch rate cost_usd() assumes.
        cost = 2.0 * sum(cost_usd(r.get("input_tokens", 0), r.get("output_tokens", 0), r.get("cached_tokens", 0)) for r in results)
        print_summary(results, cost, baseline)
        return

    mode_label = "FAIL_FAST regression guard" if FAIL_FAST else "full run"
    print(f"fullrun [model {MODEL}] — {mode_label}")
    print(f"  model={MODEL}  effort={REASONING_EFFORT}  prompt={PROMPT_FILE.name}  hash={prompt_hash}")
    print(f"  {len(pairs)} pairs in chunks of {CHUNK_SIZE}")
    print(f"  Cost limit: ${COST_LIMIT_USD}  (est. ~${cost_usd(len(pairs)*36000, len(pairs)*4400):.2f})")
    if baseline_count > 0:
        print(f"  Baseline: {baseline_count} pairs from previous run (regression detection active)")
    if FAIL_FAST:
        print(f"  FAIL_FAST=True — will stop on first FAIL/REGRESSION")
    print(f"  Results → {RESULTS_DIR.name}/")
    print()

    pairs_sig = hashlib.sha256(",".join(sorted(p["name"] for p in pairs)).encode()).hexdigest()[:12]
    state = load_state()
    if state and state.get("prompt_hash") != prompt_hash:
        print(f"Prompt changed (old={state['prompt_hash']}, new={prompt_hash}) — starting fresh.")
        state = None
    elif state and state.get("pairs_sig") != pairs_sig:
        print(f"Pair set changed (ONLY_PAIRS/SAMPLE_N differ from saved state) — starting fresh.")
        state = None

    all_results: list[dict] = []
    cumulative_cost = 0.0
    completed_chunks: set = set()

    if state:
        for cs in state.get("chunks", []):
            if cs["done"]:
                completed_chunks.add(cs["chunk_idx"])
                for name in cs["pair_names"]:
                    pair = pair_by_name.get(name)
                    if not pair:
                        continue
                    rp = RESULTS_DIR / f"{name}_{pair['category']}.json"
                    if rp.exists():
                        try:
                            saved = json.loads(rp.read_text(encoding="utf-8"))
                            meta = saved.get("_meta", {})
                            all_results.append({
                                "name":     name,
                                "category": pair["category"],
                                "expected": pair["expected"],
                                "actual":   meta.get("actual", ""),
                                "status":   meta.get("status", ""),
                                "input_tokens":  0,
                                "output_tokens": 0,
                            })
                        except Exception:
                            pass
        cumulative_cost = state.get("cumulative_cost", 0.0)
        print(f"Resuming — {len(completed_chunks)} chunks already done, cost so far ${cumulative_cost:.4f}")

    if state is None:
        state = {"prompt_hash": prompt_hash, "pairs_sig": pairs_sig, "chunks": [], "cumulative_cost": 0.0}

    chunks = [pairs[i:i+CHUNK_SIZE] for i in range(0, len(pairs), CHUNK_SIZE)]

    # Submit chunks — in FAIL_FAST mode, submit one at a time
    pending: list[dict] = []
    chunk_queue = [(i, c) for i, c in enumerate(chunks) if i not in completed_chunks]

    if FAIL_FAST:
        # Submit and poll one chunk at a time
        for chunk_idx, chunk in chunk_queue:
            existing = next((c for c in state["chunks"] if c["chunk_idx"] == chunk_idx and not c["done"]), None)
            if existing:
                print(f"  [chunk {chunk_idx+1}] Resuming batch {existing['batch_id']}", flush=True)
                cs = existing
            else:
                cs = submit_chunk(chunk, chunk_idx)
                state["chunks"] = [c for c in state["chunks"] if c["chunk_idx"] != chunk_idx]
                state["chunks"].append(cs)
                save_state(state)

            # Poll this single chunk
            while True:
                time.sleep(POLL_INTERVAL)
                batch_obj = api_call(client.batches.retrieve, cs["batch_id"])
                counts = batch_obj.request_counts
                print(f"  [chunk {chunk_idx+1}] {batch_obj.status}  {counts.completed if counts else '?'}/{counts.total if counts else '?'}", flush=True)

                if batch_obj.status in ("completed", "failed", "expired", "cancelled"):
                    results, garbage = collect_chunk(batch_obj, cs, pair_by_name, baseline)
                    delete_files(cs["file_ids"])

                    # Retry garbage pairs
                    retry_round = 0
                    while garbage and retry_round < MAX_GARBAGE_RETRIES:
                        retry_round += 1
                        print(f"\n  Retrying {len(garbage)} garbage responses (attempt {retry_round}/{MAX_GARBAGE_RETRIES})...", flush=True)
                        retry_state = submit_chunk(garbage, chunk_idx * 100 + retry_round)
                        state["chunks"].append(retry_state)
                        save_state(state)
                        while True:
                            time.sleep(POLL_INTERVAL)
                            retry_obj = api_call(client.batches.retrieve, retry_state["batch_id"])
                            if retry_obj.status in ("completed", "failed", "expired", "cancelled"):
                                retry_results, garbage = collect_chunk(retry_obj, retry_state, pair_by_name, baseline)
                                delete_files(retry_state["file_ids"])
                                results.extend(retry_results)
                                retry_state["done"] = True
                                save_state(state)
                                break

                    chunk_cost = sum(cost_usd(r.get("input_tokens", 0), r.get("output_tokens", 0), r.get("cached_tokens", 0)) for r in results)
                    cumulative_cost += chunk_cost
                    all_results.extend(results)

                    cs["done"] = True
                    state["cumulative_cost"] = cumulative_cost
                    save_state(state)

                    print_progress(all_results, len(pairs), cumulative_cost)

                    # FAIL_FAST: only stop on TRUE regressions (PASS → FAIL/REVIEW)
                    # Par that were already FAIL/REVIEW in baseline are not regressions
                    new_regressions = []
                    for r in results:
                        prev = baseline.get(r["name"])
                        if prev and prev.get("prompt_hash") != prompt_hash:
                            if prev.get("status") == "PASS" and r.get("status") in ("FAIL", "REVIEW"):
                                new_regressions.append(r)

                    if new_regressions:
                        print(f"\n{'!'*60}")
                        print(f"  FAIL_FAST triggered — {len(new_regressions)} regression(s) detected.")
                        for r in new_regressions:
                            prev = baseline[r["name"]]
                            print(f"  ⚠️REGRESSION  {r['name']:30s}  was={prev.get('actual','?')}  now={r.get('actual','?')}")
                        print(f"  State saved — fix prompt and re-run.")
                        print(f"{'!'*60}")
                        print_summary(all_results, cumulative_cost, baseline)
                        return

                    if cumulative_cost >= COST_LIMIT_USD:
                        print(f"\n  COST LIMIT REACHED: ${cumulative_cost:.4f} >= ${COST_LIMIT_USD}. Stopping.")
                        print_summary(all_results, cumulative_cost, baseline)
                        return

                    break  # chunk done, move to next
    else:
        # Normal mode: submit all chunks, then poll
        for chunk_idx, chunk in chunk_queue:
            existing = next((c for c in state["chunks"] if c["chunk_idx"] == chunk_idx and not c["done"]), None)
            if existing:
                print(f"  [chunk {chunk_idx+1}] Resuming batch {existing['batch_id']}", flush=True)
                pending.append(existing)
            else:
                cs = submit_chunk(chunk, chunk_idx)
                state["chunks"] = [c for c in state["chunks"] if c["chunk_idx"] != chunk_idx]
                state["chunks"].append(cs)
                save_state(state)
                pending.append(cs)

        print(f"\nAll {len(pending)} chunks submitted — polling until done...\n", flush=True)

        while pending:
            time.sleep(POLL_INTERVAL)
            still_pending = []
            for cs in pending:
                chunk_idx = cs["chunk_idx"]
                batch_obj = api_call(client.batches.retrieve, cs["batch_id"])
                counts = batch_obj.request_counts
                print(f"  [chunk {chunk_idx+1}] {batch_obj.status}  {counts.completed if counts else '?'}/{counts.total if counts else '?'}", flush=True)

                if batch_obj.status in ("completed", "failed", "expired", "cancelled"):
                    results, garbage = collect_chunk(batch_obj, cs, pair_by_name, baseline)
                    delete_files(cs["file_ids"])

                    # Retry garbage pairs
                    retry_round = 0
                    while garbage and retry_round < MAX_GARBAGE_RETRIES:
                        retry_round += 1
                        print(f"\n  Retrying {len(garbage)} garbage responses (attempt {retry_round}/{MAX_GARBAGE_RETRIES})...", flush=True)
                        retry_state = submit_chunk(garbage, chunk_idx * 100 + retry_round)
                        state["chunks"].append(retry_state)
                        save_state(state)
                        while True:
                            time.sleep(POLL_INTERVAL)
                            retry_obj = api_call(client.batches.retrieve, retry_state["batch_id"])
                            if retry_obj.status in ("completed", "failed", "expired", "cancelled"):
                                retry_results, garbage = collect_chunk(retry_obj, retry_state, pair_by_name, baseline)
                                delete_files(retry_state["file_ids"])
                                results.extend(retry_results)
                                retry_state["done"] = True
                                save_state(state)
                                break

                    chunk_cost = sum(cost_usd(r.get("input_tokens", 0), r.get("output_tokens", 0), r.get("cached_tokens", 0)) for r in results)
                    cumulative_cost += chunk_cost
                    all_results.extend(results)

                    cs["done"] = True
                    state["cumulative_cost"] = cumulative_cost
                    save_state(state)

                    print(f"  [chunk {chunk_idx+1}] Done. Cost: ${chunk_cost:.4f}  cumulative: ${cumulative_cost:.4f}", flush=True)
                    print_progress(all_results, len(pairs), cumulative_cost)

                    if cumulative_cost >= COST_LIMIT_USD:
                        print(f"\n  COST LIMIT REACHED: ${cumulative_cost:.4f} >= ${COST_LIMIT_USD}. Stopping.")
                        print_summary(all_results, cumulative_cost, baseline)
                        return
                else:
                    still_pending.append(cs)

            if still_pending:
                pending = still_pending
                done_count = len(all_results)
                print(f"  {len(still_pending)} chunks still running — {done_count}/{len(pairs)} pairs done so far...\n", flush=True)
            else:
                pending = []

    print_summary(all_results, cumulative_cost, baseline)


if __name__ == "__main__":
    main()
