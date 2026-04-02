"""
fullrun_54.py — Run all 242 pairs through gpt-5.4 (reasoning_effort=medium) via Batch API.

Uses api_prompt_54.md — tuned for decisive final verdicts.
Est. cost: ~$25 based on observed 36k input / 4.4k output tokens per pair.

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
PROMPT_FILE     = BASE_DIR / "api_prompt_54.md"
SCHEMA_FILE     = BASE_DIR / "schema_slim_strict.json"
STATE_FILE      = BASE_DIR / "fullrun_54_state.json"

RESULTS_DIR.mkdir(exist_ok=True)

MODEL            = "gpt-5.4"
REASONING_EFFORT = "medium"
INPUT_PRICE      = 1.875  # $/1M tokens (Batch API = 50% off 3.75)
OUTPUT_PRICE     = 7.50   # $/1M tokens (Batch API = 50% off 15.0)
COST_LIMIT_USD   = 60.0
CHUNK_SIZE       = 20
POLL_INTERVAL    = 30

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
# Pair discovery — all 242 pairs
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
    print(f"  [chunk {chunk_idx+1}] Submitting batch ({len(jsonl_bytes)/1024:.1f} KB)...", flush=True)

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

def collect_chunk(batch_obj, chunk_state: dict, pair_by_name: dict) -> list[dict]:
    if not getattr(batch_obj, "output_file_id", None):
        print(f"  [chunk {chunk_state['chunk_idx']+1}] No output — batch failed.", flush=True)
        return []

    output_text = api_call(client.files.content, batch_obj.output_file_id).text
    results = []
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
            results.append({"name": custom_id, "error": f"JSONDecodeError: {e}"})
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

        status_icon = "✓" if status == "PASS" else ("?" if status == "REVIEW" else "✗")
        print(f"    {status_icon} {custom_id:35s} {status:6s}  got={str(comparison_result):14s}  conf={conf}", flush=True)

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

    return results


# ---------------------------------------------------------------------------
# Progress / summary
# ---------------------------------------------------------------------------

def print_progress(all_results: list[dict], total: int, cumulative_cost: float):
    done    = len(all_results)
    correct = sum(1 for r in all_results if r.get("status") == "PASS")
    review  = sum(1 for r in all_results if r.get("status") == "REVIEW")
    fail    = sum(1 for r in all_results if r.get("status") == "FAIL" or "error" in r)
    print(f"\n  ┌─ PROGRESS ({'='*38})")
    print(f"  │  Done:    {done}/{total}  ({done/total*100:.0f}%)")
    print(f"  │  PASS:    {correct}  ({correct/done*100:.1f}%)" if done else "  │  PASS:    0")
    print(f"  │  REVIEW:  {review}  ({review/done*100:.1f}%)" if done else "  │  REVIEW:  0")
    print(f"  │  FAIL:    {fail}  ({fail/done*100:.1f}%)" if done else "  │  FAIL:    0")
    print(f"  │  Cost so far: ${cumulative_cost:.4f} USD  (limit: ${COST_LIMIT_USD})")
    print(f"  └{'─'*48}", flush=True)


def print_summary(all_results: list[dict], cumulative_cost: float):
    total   = len(all_results)
    correct = sum(1 for r in all_results if r.get("status") == "PASS")
    review  = sum(1 for r in all_results if r.get("status") == "REVIEW")
    fail    = sum(1 for r in all_results if r.get("status") == "FAIL" or "error" in r)
    print(f"\n{'='*60}")
    print(f"  FINAL RESULTS — {MODEL} — {total} pairs")
    print(f"  {'─'*56}")
    print(f"  PASS:   {correct:4d}  ({correct/total*100:.1f}%)" if total else "  PASS:   0")
    print(f"  REVIEW: {review:4d}  ({review/total*100:.1f}%)" if total else "  REVIEW: 0")
    print(f"  FAIL:   {fail:4d}  ({fail/total*100:.1f}%)" if total else "  FAIL:   0")
    print(f"  {'─'*56}")
    print(f"  Total cost: ${cumulative_cost:.4f} USD")
    if fail > 0:
        print(f"\n  FAILURES:")
        for r in all_results:
            if r.get("status") == "FAIL":
                print(f"    FAIL  {r['name']:30s}  expected={r['expected']:16s}  got={r['actual']:16s}  conf={r.get('confidence','?')}")
    if review > 0:
        print(f"\n  MANUAL REVIEW:")
        for r in all_results:
            if r.get("status") == "REVIEW":
                print(f"    REVIEW  {r['name']:30s}  expected={r['expected']}")
    print(f"{'='*60}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    pairs = discover_pairs()
    if not pairs:
        print("No pairs found.")
        return

    pair_by_name = {p["name"]: p for p in pairs}
    chunks = [pairs[i:i+CHUNK_SIZE] for i in range(0, len(pairs), CHUNK_SIZE)]

    print(f"fullrun_54 — model={MODEL}  effort={REASONING_EFFORT}  prompt={PROMPT_FILE.name}  hash={prompt_hash}")
    print(f"{len(pairs)} pairs in {len(chunks)} chunks of {CHUNK_SIZE}")
    print(f"Cost limit: ${COST_LIMIT_USD}  (est. ~${cost_usd(len(pairs)*36000, len(pairs)*4400):.2f} based on observed 36k/4.4k tok/pair)")

    state = load_state()
    if state and state.get("prompt_hash") != prompt_hash:
        # Prompt changed but batches already submitted with old prompt — resume collection
        print(f"Prompt changed (old={state['prompt_hash']}, new={prompt_hash}) — resuming collection of existing batches anyway.")
        # Don't reset — the batches are already running with the old prompt

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

    pending: list[dict] = []
    for chunk_idx, chunk in enumerate(chunks):
        if chunk_idx in completed_chunks:
            continue
        existing = next((c for c in state["chunks"] if c["chunk_idx"] == chunk_idx and not c["done"]), None)
        if existing:
            print(f"  [chunk {chunk_idx+1}] Resuming batch {existing['batch_id']}", flush=True)
            pending.append(existing)
        else:
            print(f"\n--- Submitting chunk {chunk_idx+1}/{len(chunks)} ---", flush=True)
            chunk_state = submit_chunk(chunk, chunk_idx)
            state["chunks"] = [c for c in state["chunks"] if c["chunk_idx"] != chunk_idx]
            state["chunks"].append(chunk_state)
            save_state(state)
            pending.append(chunk_state)

    print(f"\nAll {len(pending)} chunks submitted — polling until done...\n", flush=True)

    while pending:
        time.sleep(POLL_INTERVAL)
        still_pending = []
        for chunk_state in pending:
            chunk_idx = chunk_state["chunk_idx"]
            batch_obj = api_call(client.batches.retrieve, chunk_state["batch_id"])
            counts = batch_obj.request_counts
            print(f"  [chunk {chunk_idx+1}] {batch_obj.status}  {counts.completed if counts else '?'}/{counts.total if counts else '?'}", flush=True)

            if batch_obj.status in ("completed", "failed", "expired", "cancelled"):
                results = collect_chunk(batch_obj, chunk_state, pair_by_name)
                delete_files(chunk_state["file_ids"])

                chunk_cost = sum(cost_usd(r.get("input_tokens", 0), r.get("output_tokens", 0)) for r in results)
                cumulative_cost += chunk_cost
                all_results.extend(results)

                chunk_state["done"] = True
                state["cumulative_cost"] = cumulative_cost
                save_state(state)

                print(f"  [chunk {chunk_idx+1}] Done. Cost: ${chunk_cost:.4f}  cumulative: ${cumulative_cost:.4f}", flush=True)
                print_progress(all_results, len(pairs), cumulative_cost)

                if cumulative_cost >= COST_LIMIT_USD:
                    print(f"\n  COST LIMIT REACHED: ${cumulative_cost:.4f} >= ${COST_LIMIT_USD}. Stopping.")
                    print_summary(all_results, cumulative_cost)
                    return
            else:
                still_pending.append(chunk_state)

        if still_pending:
            pending = still_pending
            done_count = len(all_results)
            print(f"  {len(still_pending)} chunks still running — {done_count}/{len(pairs)} pairs done so far...\n", flush=True)
        else:
            pending = []

    print_progress(all_results, len(pairs), cumulative_cost)
    print_summary(all_results, cumulative_cost)


if __name__ == "__main__":
    main()
