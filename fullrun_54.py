"""
fullrun_54.py — Run document pairs through gpt-5.4 (reasoning_effort=medium) via Batch API.

Modes:
  FAIL_FAST = False  →  Full run of all 241 pairs (~$24)
  FAIL_FAST = True   →  Regression guard, stops on first FAIL (~$2-3)

Set ONLY_PAIRS to a list of pair IDs to run a subset, or None for all pairs.

Results saved to: Fullrun54Results/
State file:       fullrun_54_state.json  (resume-safe)
"""

import datetime
import hashlib
import json
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI, APIConnectionError, APITimeoutError

load_dotenv()

BASE_DIR        = Path(__file__).parent
TESTSYSTEM_DIR  = BASE_DIR / "Testdata" / "Testsystem företag"
RESULTS_DIR     = BASE_DIR / "Fullrun54Results"
BASELINE_DIR    = BASE_DIR / "Fullrun54Results"   # compare against own previous results
PROMPT_FILE     = BASE_DIR / "api_prompt_54.md"
SCHEMA_FILE     = BASE_DIR / "schema_slim_strict.json"
STATE_FILE      = BASE_DIR / "fullrun_54_state.json"

RESULTS_DIR.mkdir(exist_ok=True)

MODEL            = "gpt-5.4"
REASONING_EFFORT = "medium"
INPUT_PRICE      = 1.875  # $/1M tokens (Batch API = 50% off 3.75)
OUTPUT_PRICE     = 7.50   # $/1M tokens (Batch API = 50% off 15.0)
COST_LIMIT_USD   = 60.0
POLL_INTERVAL    = 30

# ---------------------------------------------------------------------------
# Mode settings
# ---------------------------------------------------------------------------
# FAIL_FAST: stop at first FAIL result (regression guard mode)
FAIL_FAST        = False

# Chunk size: smaller = faster FAIL_FAST reaction, larger = fewer API calls
# Recommended: 2 for FAIL_FAST, 20-50 for full runs
CHUNK_SIZE       = 50

# Filter to specific pairs, or None for all.
# Example: ["P001", "P003", "P031"]
# Targeted re-test (Regelverk 5 prompt + 20 facit changes):
#   - 20 pairs with new MISMATCH facit
#   - P013: EU origin regression risk (cert lists specific EU countries, invoice has DE not listed)
#   - P210: EU origin spot check (cert SE+DE, invoice matches — low risk)
ONLY_PAIRS       = ["P015", "P0182", "P224"]

# Max retries per pair when LLM returns unparseable/garbage JSON
MAX_GARBAGE_RETRIES = 2

# ---------------------------------------------------------------------------

client        = OpenAI()
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


def cost_usd(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * INPUT_PRICE + output_tokens * OUTPUT_PRICE) / 1_000_000


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

def discover_pairs() -> list[dict]:
    """Discover all test pairs."""
    pair_files: dict[str, dict] = {}
    for pdf in sorted(TESTSYSTEM_DIR.glob("*.pdf")):
        parts = pdf.stem.split("_")
        if len(parts) < 3 or parts[1] not in ("MATCH", "MISMATCH") or parts[2] not in ("certificate", "invoice"):
            continue
        key = f"{parts[0]}_{parts[1]}"
        pair_files.setdefault(key, {})[parts[2]] = pdf

    pairs = []
    for key in sorted(pair_files):
        docs = pair_files[key]
        if "certificate" not in docs or "invoice" not in docs:
            continue
        category = key.split("_")[1]
        pairs.append({
            "name":     key,
            "category": category,
            "expected": "IDENTICAL" if category == "MATCH" else "NOT_IDENTICAL",
            "files":    [str(docs["certificate"]), str(docs["invoice"])],
        })
    return pairs


# ---------------------------------------------------------------------------
# Upload / batch
# ---------------------------------------------------------------------------

def upload_pdfs(paths: list[str]) -> dict[str, str]:
    file_ids = {}
    for path_str in paths:
        path = Path(path_str)
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
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": [
                {"type": "file", "file": {"file_id": file_ids[f]}}
                for f in pair["files"]
            ]},
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
    all_paths = list({f for p in chunk for f in p["files"]})
    print(f"  [chunk {chunk_idx+1}] Uploading {len(all_paths)} PDFs...", flush=True)
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

        overall           = result.get("overall_assessment") or {}
        comparison_result = overall.get("comparison_result") or "PARSE_ERROR"
        is_pass           = comparison_result == pair["expected"]
        is_review         = comparison_result == "MANUAL_REVIEW"
        status            = "PASS" if is_pass else ("REVIEW" if is_review else "FAIL")
        conf              = overall.get("confidence", "?")

        # Baseline comparison
        reg_label = check_regression(custom_id, status, comparison_result, baseline)

        status_icon = "✓" if status == "PASS" else ("?" if status == "REVIEW" else "✗")
        print(f"    {status_icon} {custom_id:35s} {status:6s}  got={str(comparison_result):14s}  conf={conf}  {reg_label}", flush=True)

        results.append({
            "name":          custom_id,
            "category":      pair["category"],
            "expected":      pair["expected"],
            "actual":        comparison_result,
            "status":        status,
            "confidence":    conf,
            "input_tokens":  tok_in,
            "output_tokens": tok_out,
        })

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

    total_in  = sum(r.get("input_tokens", 0) for r in all_results)
    total_out = sum(r.get("output_tokens", 0) for r in all_results)

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

    print(f"\n  TOKENS & COST:")
    print(f"    Input tokens:       {total_in:,}")
    print(f"    Output tokens:      {total_out:,}")
    print(f"    Total cost:         ${cumulative_cost:.4f}")
    if total > 0:
        print(f"    Avg cost per pair:  ${cumulative_cost/total:.4f}")
    print(f"{'='*70}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    pairs = discover_pairs()
    if not pairs:
        print("No pairs found.")
        return

    # Filter pairs if ONLY_PAIRS is set
    if ONLY_PAIRS is not None:
        pairs = [p for p in pairs if p["name"].split("_")[0] in ONLY_PAIRS]
        if not pairs:
            print(f"No pairs matched filter: {ONLY_PAIRS}")
            return

    pair_by_name = {p["name"]: p for p in pairs}

    # Load baseline for regression detection and back up if prompt changed
    baseline = load_baseline()
    baseline_count = sum(1 for b in baseline.values() if b.get("prompt_hash") != prompt_hash)

    if baseline_count > 0:
        backup_dir = BASE_DIR / "Fullrun54Results_baseline"
        if not backup_dir.exists():
            import shutil
            shutil.copytree(RESULTS_DIR, backup_dir)
            print(f"  Baseline backed up to {backup_dir.name}/ ({baseline_count} results)")

    mode_label = "FAIL_FAST regression guard" if FAIL_FAST else "full run"
    print(f"fullrun_54 — {mode_label}")
    print(f"  model={MODEL}  effort={REASONING_EFFORT}  prompt={PROMPT_FILE.name}  hash={prompt_hash}")
    print(f"  {len(pairs)} pairs in chunks of {CHUNK_SIZE}")
    print(f"  Cost limit: ${COST_LIMIT_USD}  (est. ~${cost_usd(len(pairs)*36000, len(pairs)*4400):.2f})")
    if baseline_count > 0:
        print(f"  Baseline: {baseline_count} pairs from previous run (regression detection active)")
    if FAIL_FAST:
        print(f"  FAIL_FAST=True — will stop on first FAIL/REGRESSION")
    print(f"  Results → {RESULTS_DIR.name}/")
    print()

    state = load_state()
    if state and state.get("prompt_hash") != prompt_hash:
        print(f"Prompt changed (old={state['prompt_hash']}, new={prompt_hash}) — starting fresh.")
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
        state = {"prompt_hash": prompt_hash, "chunks": [], "cumulative_cost": 0.0}

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

                    chunk_cost = sum(cost_usd(r.get("input_tokens", 0), r.get("output_tokens", 0)) for r in results)
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

                    chunk_cost = sum(cost_usd(r.get("input_tokens", 0), r.get("output_tokens", 0)) for r in results)
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
