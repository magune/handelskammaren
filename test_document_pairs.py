import datetime
import hashlib
import json
import re
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI, APIConnectionError, APITimeoutError

load_dotenv()

BASE_DIR = Path(__file__).parent
TESTDATA_DIR = BASE_DIR / "Testdata"
TESTSYSTEM_DIR = TESTDATA_DIR / "Testsystem företag"
TESTREPORTS_DIR = BASE_DIR / "Testreports"
PROMPT_FILE = BASE_DIR / "api_prompt.md"
SCHEMA_FILE = BASE_DIR / "schema_slim_strict.json"
RUN_STATE_FILE = BASE_DIR / "batch_run_state.json"

# Set to a list of pair IDs to run ONLY those pairs, or None to run all.
# Regressionsvakt — 12 stabila par som täcker alla viktiga regelområden.
# Kör dessa efter VARJE promptändring för att fånga regressioner (~$3-4).
# Välj dessa vid regression-kontroll, annars sätt till None för full körning.
REGRESSION_GUARD = [
    "P001",   # IDENTICAL, enkel — basfall consignor/consignee/goods
    "P003",   # NOT_IDENTICAL, hög konfidens — tydlig MISMATCH
    "P005",   # NOT_IDENTICAL — consignee mismatch
    "P008",   # IDENTICAL — EU-normalisering origin
    "P019",   # IDENTICAL — HK/China-normalisering (vår fix)
    "P072",   # IDENTICAL — summering rader + EU origin
    "P087",   # IDENTICAL — artikelnummer-matchning
    "P0103",  # NOT_IDENTICAL — fakturareferens + origin mismatch
    "P0118",  # IDENTICAL — fullständig verifiering
    "P0120",  # NOT_IDENTICAL — consignee annan adress
    "P0132",  # IDENTICAL — LC-undantag (täcker LC-reglerna)
    "P231",   # NOT_IDENTICAL — hög konfidens mismatch
]

ONLY_PAIRS = [
    # P0158 re-test after prompt fix (was FAIL); P014,P0147-P0157,P0159 skipped (tested with prev prompt, re-run later)
    'P0158', 'P015', 'P016',
    'P0160', 'P0161', 'P0162', 'P0163', 'P0164', 'P0165', 'P0166', 'P0167',
    'P0168', 'P0169', 'P017', 'P0170', 'P0171', 'P0172', 'P0173', 'P0174',
    'P0175', 'P0176', 'P0177', 'P0178', 'P0179', 'P018', 'P0180', 'P0181',
    'P0182', 'P0183', 'P0184', 'P0185', 'P0186', 'P0187', 'P0188', 'P0189',
    'P0190', 'P0191', 'P0192', 'P0193', 'P0194', 'P020', 'P021', 'P022',
    'P023', 'P024', 'P025', 'P026', 'P027', 'P028', 'P029', 'P030', 'P031',
    'P032', 'P033', 'P034', 'P035', 'P036', 'P037', 'P038', 'P039', 'P040',
    'P041', 'P042', 'P043', 'P044', 'P045', 'P046', 'P047', 'P048', 'P049',
    'P050', 'P051', 'P052', 'P053', 'P054', 'P055', 'P056', 'P057', 'P058',
    'P059', 'P060', 'P061', 'P062', 'P063', 'P064', 'P065', 'P066', 'P067',
    'P068', 'P069', 'P075', 'P076', 'P077', 'P078', 'P079', 'P080', 'P081',
    'P082', 'P083', 'P084', 'P090', 'P091', 'P092', 'P093', 'P094', 'P095',
    'P096', 'P097', 'P098', 'P099', 'P196', 'P197', 'P198', 'P199', 'P200',
    'P201', 'P202', 'P203', 'P204', 'P205', 'P206', 'P207', 'P208', 'P209',
    'P210', 'P216', 'P217', 'P218', 'P219', 'P220', 'P221', 'P222', 'P223',
    'P224', 'P225', 'P226', 'P227', 'P228', 'P229', 'P230', 'P236', 'P237',
    'P238', 'P239', 'P240',
]  # Fail-fast: 145 par (13 recently tested pairs skipped; re-add after full run)

# Max pairs per batch submission — smaller = faster first results
BATCH_CHUNK_SIZE = 2

# Max number of OpenAI batches running simultaneously.
# With FAIL_FAST=True, keep this at 1 to stop immediately on first FAIL with
# minimal wasted cost (at most BATCH_CHUNK_SIZE pairs already submitted).
MAX_CONCURRENT_BATCHES = 1

# Stop immediately when a FAIL is detected. Already-submitted batches are
# preserved in batch_run_state.json and will be resumed on next run.
# With small MAX_CONCURRENT_BATCHES, at most MAX_CONCURRENT_BATCHES*BATCH_CHUNK_SIZE
# pairs are "at risk" when a FAIL is found (i.e. already submitted but not yet seen).
FAIL_FAST = True

# Retry settings for network errors
MAX_RETRIES = 20
RETRY_BASE_DELAY = 15   # seconds
RETRY_MAX_DELAY = 300   # 5 minutes cap
POLL_INTERVAL = 30      # seconds between batch status checks

TESTREPORTS_DIR.mkdir(exist_ok=True)

client = OpenAI()
system_prompt = PROMPT_FILE.read_text(encoding="utf-8")
prompt_hash = hashlib.sha256(system_prompt.encode()).hexdigest()[:12]
schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Resilient API wrapper
# ---------------------------------------------------------------------------

def api_call(func, *args, **kwargs):
    """Call an OpenAI API function, retrying forever on network/timeout errors."""
    delay = RETRY_BASE_DELAY
    attempt = 0
    while True:
        try:
            return func(*args, **kwargs)
        except (APIConnectionError, APITimeoutError) as e:
            attempt += 1
            print(f"  [network error #{attempt}] {e}")
            print(f"  Retrying in {delay}s... (disconnect laptop safe, will resume)")
            time.sleep(delay)
            delay = min(delay * 2, RETRY_MAX_DELAY)
        except Exception as e:
            # Re-raise non-network errors immediately
            raise


# ---------------------------------------------------------------------------
# Document pair discovery
# ---------------------------------------------------------------------------

def get_document_pairs() -> list[dict]:
    """Discover all document pairs from Testsystem företag."""
    if not TESTSYSTEM_DIR.exists():
        print(f"WARNING: {TESTSYSTEM_DIR} not found")
        return []

    pair_files: dict[str, dict[str, Path]] = {}
    for pdf in sorted(TESTSYSTEM_DIR.glob("*.pdf")):
        parts = pdf.stem.split("_")
        if len(parts) < 3 or parts[1] not in ("MATCH", "MISMATCH") or parts[2] not in ("certificate", "invoice"):
            print(f"WARNING: Unexpected filename format, skipping: {pdf.name}")
            continue
        pair_key = f"{parts[0]}_{parts[1]}"
        pair_files.setdefault(pair_key, {})[parts[2]] = pdf

    pairs = []
    for pair_key in sorted(pair_files):
        docs = pair_files[pair_key]
        if "certificate" not in docs or "invoice" not in docs:
            print(f"WARNING: {pair_key} missing certificate or invoice, skipping")
            continue
        match_status = pair_key.split("_")[1]
        pairs.append({
            "name": pair_key,
            "category": match_status,
            "expected": "IDENTICAL" if match_status == "MATCH" else "NOT_IDENTICAL",
            "files": [str(docs["certificate"]), str(docs["invoice"])],
        })
    return pairs


def report_path_for(pair_name: str, category: str) -> Path:
    safe = re.sub(r"[^\w\-]", "_", pair_name)
    return TESTREPORTS_DIR / f"{safe}_{category}.json"


def already_collected(pair: dict) -> bool:
    """True if a result file exists AND was produced by the current prompt."""
    rp = report_path_for(pair["name"], pair["category"])
    if not rp.exists():
        return False
    try:
        meta = json.loads(rp.read_text(encoding="utf-8")).get("_meta", {})
        return meta.get("prompt_hash") == prompt_hash
    except Exception:
        return False


def report_mtime(pair: dict) -> float:
    """Return mtime of existing report, or 0.0 if no report exists."""
    rp = report_path_for(pair["name"], pair["category"])
    try:
        return rp.stat().st_mtime
    except FileNotFoundError:
        return 0.0


def sort_pairs_by_test_priority(pairs: list[dict]) -> list[dict]:
    """
    Sort pairs so we find new problems as cheaply as possible:
      1. Never-tested pairs first (no report file) — highest priority
      2. Oldest-tested pairs next (stale results)
      3. Most-recently-tested pairs last — least likely to have changed

    Within each group, preserve original alphabetical order.
    """
    never_tested = [p for p in pairs if report_mtime(p) == 0.0]
    tested = sorted(
        [p for p in pairs if report_mtime(p) > 0.0],
        key=lambda p: report_mtime(p),
    )
    return never_tested + tested


# ---------------------------------------------------------------------------
# File upload
# ---------------------------------------------------------------------------

def upload_pdfs(paths: list[str]) -> dict[str, str]:
    """Upload PDF files to OpenAI. Returns {local_path: file_id}."""
    file_ids = {}
    for path_str in paths:
        path = Path(path_str)
        print(f"    Uploading {path.name}...", flush=True)
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


# ---------------------------------------------------------------------------
# Batch construction & submission
# ---------------------------------------------------------------------------

def build_request(pair: dict, file_ids: dict[str, str]) -> dict:
    content = [
        {"type": "file", "file": {"file_id": file_ids[f]}}
        for f in pair["files"]
    ]
    return {
        "custom_id": pair["name"],
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": "gpt-5.4",
            "reasoning_effort": "high",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "verification_output",
                    "strict": True,
                    "schema": schema,
                },
            },
        },
    }


def submit_chunk(chunk: list[dict], chunk_index: int) -> dict:
    """Upload PDFs and submit batch for one chunk. Returns chunk state dict."""
    print(f"\n  [chunk {chunk_index+1}] Uploading {len(chunk)*2} PDFs...")
    all_paths = list({f for p in chunk for f in p["files"]})
    file_ids = upload_pdfs(all_paths)

    lines = [json.dumps(build_request(p, file_ids), ensure_ascii=False) for p in chunk]
    jsonl_bytes = "\n".join(lines).encode("utf-8")

    print(f"  [chunk {chunk_index+1}] Submitting batch ({len(jsonl_bytes)/1024:.1f} KB)...")
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
    print(f"  [chunk {chunk_index+1}] Batch submitted: {batch.id}")

    return {
        "chunk_index": chunk_index,
        "batch_id": batch.id,
        "pair_names": [p["name"] for p in chunk],
        "file_ids": file_ids,
        "results_collected": False,
    }


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------

def save_state(state: dict):
    RUN_STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def load_state():
    if RUN_STATE_FILE.exists():
        return json.loads(RUN_STATE_FILE.read_text(encoding="utf-8"))
    return None


# ---------------------------------------------------------------------------
# Result collection
# ---------------------------------------------------------------------------

def collect_results(batch_obj, chunk_state: dict, pair_by_name: dict[str, dict]) -> list[dict]:
    """Download and process results for a completed batch."""
    if not getattr(batch_obj, "output_file_id", None):
        print(f"  [chunk {chunk_state['chunk_index']+1}] No output file — batch may have failed entirely.")
        if getattr(batch_obj, "error_file_id", None):
            errors = api_call(client.files.content, batch_obj.error_file_id).text
            print("  Batch errors:")
            for line in errors.strip().splitlines()[:10]:
                print(f"    {line}")
        return []

    output_text = api_call(client.files.content, batch_obj.output_file_id).text
    results = []
    for line in output_text.strip().splitlines():
        entry = json.loads(line)
        custom_id = entry["custom_id"]
        pair = pair_by_name.get(custom_id)
        if pair is None:
            print(f"  WARNING: unknown custom_id: {custom_id}")
            continue
        error = entry.get("error")
        response_body = entry.get("response", {}).get("body", {})
        if error or not response_body:
            print(f"  ERROR for {custom_id}: {error}")
            results.append({"name": custom_id, "error": str(error)})
            continue
        message = response_body["choices"][0]["message"]
        result = json.loads(message["content"])
        usage = response_body.get("usage", {})
        results.append(print_pair_result(
            pair, result,
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
        ))
    return results


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def print_pair_result(pair: dict, result: dict, input_tokens: int, output_tokens: int) -> dict:
    name = pair["name"]
    overall = result["overall_assessment"]
    comparison_result = overall["comparison_result"]

    is_pass = comparison_result == pair["expected"]
    is_manual_review = comparison_result == "MANUAL_REVIEW"
    status = "PASS" if is_pass else ("REVIEW" if is_manual_review else "FAIL")

    print(f"\n{'='*60}")
    print(f"  {name} ({pair['category']})")
    print(f"  Expected: {pair['expected']}  |  Result: {comparison_result} — {status}")
    print(f"  Confidence: {overall.get('confidence','N/A')}  |  Workflow: {overall.get('workflow_recommendation','N/A')}")
    if overall.get("decision_summary"):
        print(f"\n  {overall['decision_summary']}")

    ra = result.get("rule_activation", {})
    active_flags = [lbl for key, lbl in [
        ("lc_exception_active", "LC exception"),
        ("general_goods_description_with_invoice_reference_active", "General goods + invoice ref"),
        ("mixed_origins_rule_active", "Mixed origins"),
        ("to_order_rule_active", "To order"),
        ("eu_origin_normalization_active", "EU normalization"),
    ] if ra.get(key)]
    if ra.get("quantity_exception_applied"):
        active_flags.append(f"Quantity exception {ra['quantity_exception_applied']}")
    if active_flags:
        print(f"  Active rules: {', '.join(active_flags)}")

    cp = result.get("control_points", {})
    cp_labels = {
        "consignor": "4.1 Consignor",
        "consignee": "4.2 Consignee",
        "goods_description": "4.3 Varubeskrivning",
        "quantity": "4.4 Kvantitet",
        "origin": "4.5 Ursprung",
    }
    print(f"\n  {'─'*56}")
    for cp_name, cp_label in cp_labels.items():
        point = cp.get(cp_name, {})
        cp_status = point.get("status", "N/A")
        marker = {"MATCH": "PASS", "MISMATCH": "FAIL", "NOT_APPLICABLE": "SKIP", "MANUAL_REVIEW": "WARN"}.get(cp_status, "?")
        print(f"  [{marker}] {cp_label}: {cp_status}  (conf={point.get('confidence','?')})")
        if cp_status in ("MISMATCH", "MANUAL_REVIEW", "NOT_FOUND"):
            m = point.get("motivation", "")
            if m:
                print(f"        {m[:200]}")

    if overall.get("critical_failures"):
        print(f"\n  CRITICAL FAILURES:")
        for f in overall["critical_failures"]:
            print(f"    ✗ {f}")
    if overall.get("manual_review_triggers"):
        print(f"\n  MANUAL REVIEW TRIGGERS:")
        for t in overall["manual_review_triggers"]:
            print(f"    ? {t}")

    print(f"\n  Tokens — Input: {input_tokens:,}, Output: {output_tokens:,}")

    # Save report with metadata
    result["_meta"] = {
        "tested_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "prompt_hash": prompt_hash,
        "pair": name,
        "expected": pair["expected"],
        "actual": comparison_result,
        "status": status,
    }
    report_path_for(name, pair["category"]).write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return {
        "name": name,
        "category": pair["category"],
        "expected": pair["expected"],
        "actual": comparison_result,
        "status": status,
        "workflow": overall.get("workflow_recommendation", "N/A"),
        "manual_review_triggers": overall.get("manual_review_triggers", []),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


def print_progress(all_results: list[dict], total_pairs: int):
    """Print a compact running progress line after each collected batch."""
    done = len(all_results)
    if done == 0:
        return
    correct   = sum(1 for r in all_results if r.get("status") == "PASS")
    review    = sum(1 for r in all_results if r.get("status") == "REVIEW")
    wrong     = sum(1 for r in all_results if r.get("status") == "FAIL" or "error" in r)
    acceptable = correct + review
    pct_ok    = acceptable / done * 100
    pct_wrong = wrong / done * 100
    remaining = total_pairs - done
    tokens_in  = sum(r.get("input_tokens", 0) for r in all_results)
    tokens_out = sum(r.get("output_tokens", 0) for r in all_results)
    est_cost   = (tokens_in * 7.5 + tokens_out * 30.0) / 1_000_000

    print(f"\n  ┌─ PROGRESS ({'='*40})")
    print(f"  │  Klara:       {done}/{total_pairs}  ({done/total_pairs*100:.0f}%)  — {remaining} kvar")
    print(f"  │  Rätt (PASS): {correct:4d}  ({correct/done*100:.1f}%)")
    print(f"  │  Review:      {review:4d}  ({review/done*100:.1f}%)  ← acceptabelt")
    print(f"  │  Fel  (FAIL): {wrong:4d}  ({wrong/done*100:.1f}%)")
    print(f"  │  Acceptabla:  {acceptable:4d}  ({pct_ok:.1f}%)  │  Felaktiga: {wrong}  ({pct_wrong:.1f}%)")
    print(f"  │  Kostnad hittills: ~${est_cost:.2f} USD")
    print(f"  └{'─'*50}")


def print_summary(results: list[dict]):
    total = len(results)
    correct     = sum(1 for r in results if r.get("status") == "PASS")
    review      = sum(1 for r in results if r.get("status") == "REVIEW")
    wrong       = sum(1 for r in results if r.get("status") == "FAIL" or "error" in r)
    acceptable  = correct + review

    total_in  = sum(r.get("input_tokens", 0) for r in results)
    total_out = sum(r.get("output_tokens", 0) for r in results)
    est_cost  = (total_in * 7.5 + total_out * 30.0) / 1_000_000

    print(f"\n{'='*60}")
    print(f"  SLUTRESULTAT: {total} dokumentpar testade")
    print(f"  {'─'*56}")
    print(f"  Rätt         (PASS):          {correct:4d}  ({correct/total*100:.1f}%)")
    print(f"  Manuell gr.  (REVIEW):        {review:4d}  ({review/total*100:.1f}%)  ← ej fel")
    print(f"  Fel          (FAIL):          {wrong:4d}  ({wrong/total*100:.1f}%)")
    print(f"  {'─'*56}")
    print(f"  Acceptabel precision:         {acceptable:4d}/{total}  ({acceptable/total*100:.1f}%)")
    print(f"  Felprocent:                   {wrong:4d}/{total}  ({wrong/total*100:.1f}%)")
    print(f"  {'─'*56}")

    if wrong > 0 or any("error" in r for r in results):
        print(f"\n  FELKLASSADE PAR:")
        for r in results:
            if "error" in r:
                print(f"    ERROR   {r['name']}: {r['error']}")
            elif r.get("status") == "FAIL":
                print(f"    FAIL    {r['name']:30s}  expected={r['expected']:16s}  got={r['actual']}")

    if review > 0:
        print(f"\n  MANUAL_REVIEW (kräver mänsklig granskning):")
        for r in results:
            if r.get("status") == "REVIEW":
                print(f"    REVIEW  {r['name']:30s}  expected={r['expected']}")
                for t in r.get("manual_review_triggers", []):
                    print(f"            ? {t}")

    print(f"\n  Tokens — Input: {total_in:,}, Output: {total_out:,}")
    print(f"  Kostnad (Batch API ~50% rabatt): ~${est_cost:.2f} USD")
    print(f"{'='*60}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def poll_until_done(pending_batches: list[dict], state: dict, pair_by_name: dict,
                    all_results: list[dict], all_pairs: list[dict]) -> str:
    """
    Poll pending_batches until all finish (or FAIL_FAST triggers).

    Returns:
      "done"      — all batches finished normally
      "fail_fast" — a FAIL was detected; state is saved for resume
    """
    while pending_batches:
        still_pending = []
        for chunk_state in pending_batches:
            batch_id = chunk_state["batch_id"]
            try:
                batch_obj = api_call(client.batches.retrieve, batch_id)
            except Exception as e:
                print(f"  Could not retrieve batch {batch_id}: {e}")
                still_pending.append(chunk_state)
                continue

            counts = batch_obj.request_counts
            completed = counts.completed if counts else "?"
            total_ct = counts.total if counts else "?"
            idx = chunk_state["chunk_index"] + 1
            print(f"  [chunk {idx:2d}] {batch_obj.status:12s}  {completed}/{total_ct} completed", flush=True)

            if batch_obj.status in ("completed", "failed", "expired", "cancelled"):
                print(f"\n  [chunk {idx}] Collecting results...")
                chunk_pairs = [pair_by_name[n] for n in chunk_state["pair_names"] if n in pair_by_name]
                chunk_pair_by_name = {p["name"]: p for p in chunk_pairs}
                results = collect_results(batch_obj, chunk_state, chunk_pair_by_name)

                completed_count = batch_obj.request_counts.completed if batch_obj.request_counts else 0
                if completed_count == 0 and batch_obj.status == "failed":
                    print(f"  [chunk {idx}] Batch failed with 0 results — will retry on next run.")
                    chunk_state["results_collected"] = False
                    chunk_state["batch_id"] = None
                else:
                    all_results.extend(results)
                    chunk_state["results_collected"] = True

                delete_files(chunk_state.get("file_ids", {}))
                save_state(state)

                done_batches = sum(1 for b in state["batches"] if b["results_collected"])
                total_batches = len(state["batches"])
                print(f"  [chunk {idx}] Done. ({done_batches}/{total_batches} batchar klara)")
                print_progress(all_results, len(all_pairs))

                # FAIL_FAST check — scan newly collected results
                if FAIL_FAST:
                    new_fails = [r for r in results if r.get("status") == "FAIL"]
                    if new_fails:
                        print(f"\n{'!'*60}")
                        print(f"  FAIL_FAST triggered — stopping immediately.")
                        for r in new_fails:
                            print(f"  FAIL  {r['name']:30s}  expected={r['expected']:16s}  got={r['actual']}")
                        print(f"  State preserved in {RUN_STATE_FILE.name} — resume after fixing prompt.")
                        print(f"{'!'*60}")
                        return "fail_fast"
            else:
                still_pending.append(chunk_state)

        if still_pending:
            pending_batches = still_pending
            print(f"\n  {len(still_pending)} batches still running — checking again in {POLL_INTERVAL}s...")
            time.sleep(POLL_INTERVAL)
        else:
            pending_batches = []

    return "done"


def main():
    all_pairs = get_document_pairs()
    active_filter = ONLY_PAIRS if ONLY_PAIRS is not None else None
    if active_filter is not None:
        # p["name"] is like "P002_MATCH" — match on pair ID prefix (up to first underscore)
        all_pairs = [p for p in all_pairs if p["name"].split("_")[0] in active_filter]
    if not all_pairs:
        print(f"No document pairs found.")
        return

    # When running all pairs, sort so untested/stale pairs come first.
    # This lets FAIL_FAST catch new problems before retesting stable pairs.
    if active_filter is None:
        all_pairs = sort_pairs_by_test_priority(all_pairs)

    pair_by_name = {p["name"]: p for p in all_pairs}
    chunks = [all_pairs[i:i + BATCH_CHUNK_SIZE] for i in range(0, len(all_pairs), BATCH_CHUNK_SIZE)]

    # -----------------------------------------------------------------------
    # Load or build run state
    # -----------------------------------------------------------------------
    state = load_state()

    if state is not None:
        # Verify the saved run matches the current pair list
        saved_names = {n for b in state["batches"] for n in b["pair_names"]}
        current_names = {p["name"] for p in all_pairs}
        if saved_names != current_names:
            print("WARNING: Saved state does not match current pair list — starting fresh.")
            state = None

    # -----------------------------------------------------------------------
    # Collect already-done pairs from existing report files (before any API calls)
    # -----------------------------------------------------------------------
    all_results: list[dict] = []
    for p in all_pairs:
        if already_collected(p):
            rp = report_path_for(p["name"], p["category"])
            try:
                result = json.loads(rp.read_text(encoding="utf-8"))
                overall = result["overall_assessment"]
                comparison_result = overall["comparison_result"]
                is_pass = comparison_result == p["expected"]
                is_manual = comparison_result == "MANUAL_REVIEW"
                status = "PASS" if is_pass else ("REVIEW" if is_manual else "FAIL")
                all_results.append({
                    "name": p["name"],
                    "category": p["category"],
                    "expected": p["expected"],
                    "actual": comparison_result,
                    "status": status,
                    "workflow": overall.get("workflow_recommendation", "N/A"),
                    "manual_review_triggers": overall.get("manual_review_triggers", []),
                    "input_tokens": 0,
                    "output_tokens": 0,
                })
            except Exception:
                pass

    if state is None:
        # -----------------------------------------------------------------------
        # Fresh run: submit and poll one wave at a time (fail-fast friendly)
        # -----------------------------------------------------------------------
        mode = "sequential waves" if FAIL_FAST else f"up to {MAX_CONCURRENT_BATCHES} concurrent"
        print(f"\nRunning {len(all_pairs)} pairs in {len(chunks)} chunks of {BATCH_CHUNK_SIZE} ({mode})...")
        if FAIL_FAST:
            print(f"FAIL_FAST=True: submitting {MAX_CONCURRENT_BATCHES} batch(es) at a time — stopping on first FAIL.\n")

        batch_states: list[dict] = []
        chunk_queue = list(enumerate(chunks))  # (original_index, chunk)

        while chunk_queue:
            # Submit up to MAX_CONCURRENT_BATCHES new batches
            wave: list[dict] = []
            while chunk_queue and len(wave) < MAX_CONCURRENT_BATCHES:
                i, chunk = chunk_queue.pop(0)
                pending = [p for p in chunk if not already_collected(p)]
                if not pending:
                    print(f"  [chunk {i+1}] All pairs already done, skipping.")
                    already_done_state = {
                        "chunk_index": i,
                        "batch_id": None,
                        "pair_names": [p["name"] for p in chunk],
                        "file_ids": {},
                        "results_collected": True,
                    }
                    batch_states.append(already_done_state)
                    # Don't count skipped chunks against wave size — keep pulling
                    continue
                chunk_state = submit_chunk(pending, i)
                batch_states.append(chunk_state)
                wave.append(chunk_state)

            if not wave:
                # All remaining chunks were already done
                continue

            state = {"batches": batch_states}
            save_state(state)

            # Poll this wave to completion (or FAIL_FAST)
            outcome = poll_until_done(wave, state, pair_by_name, all_results, all_pairs)
            if outcome == "fail_fast":
                return  # State saved; resume after prompt fix

        state = {"batches": batch_states}
        save_state(state)

    else:
        # -----------------------------------------------------------------------
        # Resume from saved state
        # -----------------------------------------------------------------------
        print(f"\nResuming run from saved state ({len(state['batches'])} batches)...")

        # Reset batches that failed with 0 results so they get resubmitted
        for b in state["batches"]:
            if b.get("results_collected") and b.get("batch_id"):
                has_results = any(
                    already_collected(pair_by_name[n])
                    for n in b["pair_names"]
                    if n in pair_by_name
                )
                if not has_results:
                    print(f"  [chunk {b['chunk_index']+1}] Re-queuing — previously failed with 0 results.")
                    b["results_collected"] = False
                    b["batch_id"] = None
        save_state(state)

        # Resubmit failed chunks in waves (same fail-fast logic)
        needs_submit = [b for b in state["batches"] if not b["results_collected"] and not b["batch_id"]]
        if needs_submit:
            print(f"  Resubmitting {len(needs_submit)} failed chunks in waves of {MAX_CONCURRENT_BATCHES}...")
            queue = list(needs_submit)
            while queue:
                wave = queue[:MAX_CONCURRENT_BATCHES]
                queue = queue[MAX_CONCURRENT_BATCHES:]
                for b in wave:
                    chunk = [pair_by_name[n] for n in b["pair_names"] if n in pair_by_name]
                    pending = [p for p in chunk if not already_collected(p)]
                    if pending:
                        new_state = submit_chunk(pending, b["chunk_index"])
                        b.update(new_state)
                    else:
                        b["results_collected"] = True
                save_state(state)

                active_wave = [b for b in wave if b.get("batch_id") and not b["results_collected"]]
                if active_wave:
                    outcome = poll_until_done(active_wave, state, pair_by_name, all_results, all_pairs)
                    if outcome == "fail_fast":
                        return

        # Poll any already-submitted-but-not-collected batches
        pending_batches = [b for b in state["batches"] if not b["results_collected"] and b["batch_id"]]
        if pending_batches:
            outcome = poll_until_done(pending_batches, state, pair_by_name, all_results, all_pairs)
            if outcome == "fail_fast":
                return

    # -----------------------------------------------------------------------
    # Final summary and cleanup
    # -----------------------------------------------------------------------
    run_pair_names = {p["name"] for p in all_pairs}
    run_results = [r for r in all_results if r["name"] in run_pair_names]
    print_summary(run_results)

    all_collected = all(b["results_collected"] for b in state["batches"] if b["batch_id"])
    if all_collected:
        RUN_STATE_FILE.unlink(missing_ok=True)
        print("Run complete. State file removed.")


if __name__ == "__main__":
    main()
