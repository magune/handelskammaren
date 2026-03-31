"""
o4mini_fullrun.py — Run all 242 pairs through o4-mini (reasoning_effort=low) with a $25 cost kill switch.

Submits pairs in chunks of 20 via Batch API. After each chunk completes, checks
cumulative cost and aborts if it would exceed COST_LIMIT_USD.

Results saved to: O4MiniFullrunResults/
State file:       o4mini_fullrun_state.json  (resume-safe)
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
RESULTS_DIR     = BASE_DIR / "O4MiniFullrunResults"
PROMPT_FILE     = BASE_DIR / "api_prompt.md"
SCHEMA_FILE     = BASE_DIR / "schema_slim_strict.json"
STATE_FILE      = BASE_DIR / "o4mini_fullrun_state.json"

RESULTS_DIR.mkdir(exist_ok=True)

MODEL           = "o4-mini"
INPUT_PRICE     = 0.55   # $/1M tokens (Batch API)
OUTPUT_PRICE    = 2.20   # $/1M tokens (Batch API)
COST_LIMIT_USD  = 25.0   # hard stop if cumulative cost exceeds this
CHUNK_SIZE      = 20     # pairs per batch submission
POLL_INTERVAL   = 30     # seconds between status checks

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
# Pair discovery
# ---------------------------------------------------------------------------

def discover_pairs() -> list[dict]:
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
    return {
        "custom_id": pair["name"],
        "method":    "POST",
        "url":       "/v1/chat/completions",
        "body": {
            "model": MODEL,
            "reasoning_effort": "low",
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
        },
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
        entry      = json.loads(line)
        custom_id  = entry["custom_id"]
        pair       = pair_by_name.get(custom_id)
        if pair is None:
            continue
        error = entry.get("error")
        body  = entry.get("response", {}).get("body", {})
        if error or not body:
            results.append({"name": custom_id, "error": str(error)})
            continue
        message = body["choices"][0]["message"]
        result  = json.loads(message["content"])
        usage   = body.get("usage", {})
        tok_in  = usage.get("prompt_tokens", 0)
        tok_out = usage.get("completion_tokens", 0)

        overall            = result["overall_assessment"]
        comparison_result  = overall["comparison_result"]
        is_pass            = comparison_result == pair["expected"]
        is_review          = comparison_result == "MANUAL_REVIEW"
        status             = "PASS" if is_pass else ("REVIEW" if is_review else "FAIL")

        results.append({
            "name":       custom_id,
            "category":   pair["category"],
            "expected":   pair["expected"],
            "actual":     comparison_result,
            "status":     status,
            "confidence": overall.get("confidence", "N/A"),
            "input_tokens":  tok_in,
            "output_tokens": tok_out,
        })

        # Save per-pair report
        result["_meta"] = {
            "tested_at":   datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "prompt_hash": prompt_hash,
            "model":       MODEL,
            "pair":        custom_id,
            "expected":    pair["expected"],
            "actual":      comparison_result,
            "status":      status,
        }
        out_path = RESULTS_DIR / f"{custom_id}_{pair['category']}.json"
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    return results


# ---------------------------------------------------------------------------
# Progress / summary printing
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
    print(f"  PASS:   {correct:4d}  ({correct/total*100:.1f}%)")
    print(f"  REVIEW: {review:4d}  ({review/total*100:.1f}%)")
    print(f"  FAIL:   {fail:4d}  ({fail/total*100:.1f}%)")
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

    print(f"mini_fullrun — model={MODEL}  prompt={prompt_hash}")
    print(f"{len(pairs)} pairs in {len(chunks)} chunks of {CHUNK_SIZE}")
    print(f"Cost limit: ${COST_LIMIT_USD}  (est. max ~${cost_usd(len(pairs)*5000, len(pairs)*500):.2f} at 5k/500 tok/pair)")

    state = load_state()
    if state and state.get("prompt_hash") != prompt_hash:
        print("Prompt changed — starting fresh.")
        state = None

    all_results: list[dict] = []
    cumulative_cost = 0.0
    completed_chunks: set = set()

    if state:
        # Restore already-completed chunk results from saved reports
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

    # Process chunks one at a time (sequential to enable cost kill switch)
    for chunk_idx, chunk in enumerate(chunks):
        if chunk_idx in completed_chunks:
            continue

        print(f"\n--- Chunk {chunk_idx+1}/{len(chunks)} ---", flush=True)

        # Pre-flight cost check: would starting this chunk risk exceeding limit?
        # Estimate: ~5000 input + 500 output tokens per pair
        est_chunk_cost = cost_usd(len(chunk) * 5000, len(chunk) * 500)
        if cumulative_cost + est_chunk_cost > COST_LIMIT_USD * 1.1:  # 10% buffer
            print(f"\n  COST LIMIT WARNING: estimated cumulative ${cumulative_cost + est_chunk_cost:.2f} would exceed ${COST_LIMIT_USD} limit.")
            print(f"  Stopping before chunk {chunk_idx+1}.")
            break

        chunk_state = submit_chunk(chunk, chunk_idx)

        # Update state
        if state is None:
            state = {"prompt_hash": prompt_hash, "chunks": [], "cumulative_cost": 0.0}
        # Remove any existing entry for this chunk_idx
        state["chunks"] = [c for c in state["chunks"] if c["chunk_idx"] != chunk_idx]
        state["chunks"].append(chunk_state)
        save_state(state)

        # Poll until this chunk completes
        while True:
            time.sleep(POLL_INTERVAL)
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

                print(f"  [chunk {chunk_idx+1}] Chunk cost: ${chunk_cost:.4f}  cumulative: ${cumulative_cost:.4f}", flush=True)
                print_progress(all_results, len(pairs), cumulative_cost)

                # Kill switch
                if cumulative_cost >= COST_LIMIT_USD:
                    print(f"\n  COST LIMIT REACHED: ${cumulative_cost:.4f} >= ${COST_LIMIT_USD}. Stopping.")
                    print_summary(all_results, cumulative_cost)
                    return
                break

    # -----------------------------------------------------------------------
    # Re-run failures 2 more times to get 3-sample majority vote
    # -----------------------------------------------------------------------
    failed = [r for r in all_results if r.get("status") == "FAIL"]
    if failed:
        print(f"\n{'─'*60}")
        print(f"  Re-running {len(failed)} failed pair(s) x2 for majority vote...")
        rerun_pairs = [pair_by_name[r["name"]] for r in failed if r["name"] in pair_by_name]

        for run_num in range(2):
            print(f"\n  --- Re-run {run_num+1}/2 ---", flush=True)
            rerun_chunk_state = submit_chunk(rerun_pairs, chunk_idx=9000 + run_num)

            while True:
                time.sleep(POLL_INTERVAL)
                batch_obj = api_call(client.batches.retrieve, rerun_chunk_state["batch_id"])
                counts = batch_obj.request_counts
                print(f"  [rerun {run_num+1}] {batch_obj.status}  {counts.completed if counts else '?'}/{counts.total if counts else '?'}", flush=True)
                if batch_obj.status in ("completed", "failed", "expired", "cancelled"):
                    rerun_results = collect_chunk(batch_obj, rerun_chunk_state, pair_by_name)
                    delete_files(rerun_chunk_state["file_ids"])
                    chunk_cost = sum(cost_usd(r.get("input_tokens", 0), r.get("output_tokens", 0)) for r in rerun_results)
                    cumulative_cost += chunk_cost
                    print(f"  [rerun {run_num+1}] cost: ${chunk_cost:.4f}  cumulative: ${cumulative_cost:.4f}", flush=True)

                    # Merge rerun results into a per-name votes dict
                    for r in rerun_results:
                        name = r["name"]
                        rp = RESULTS_DIR / f"{name}_{pair_by_name[name]['category']}_rerun{run_num+1}.json"
                        rp.write_text(json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")
                    break

        # Tally votes: collect all 3 results per failed pair
        print(f"\n  MAJORITY VOTE RESULTS (3 runs):")
        print(f"  {'─'*56}")
        for orig in failed:
            name     = orig["name"]
            pair     = pair_by_name.get(name)
            if not pair:
                continue
            votes = [orig["actual"]]
            for run_num in range(2):
                rp = RESULTS_DIR / f"{name}_{pair['category']}_rerun{run_num+1}.json"
                if rp.exists():
                    try:
                        saved = json.loads(rp.read_text(encoding="utf-8"))
                        votes.append(saved.get("actual", ""))
                    except Exception:
                        pass
            # Majority = most common vote
            majority = max(set(votes), key=votes.count)
            correct  = majority == pair["expected"]
            marker   = "PASS" if correct else "FAIL"
            print(f"  [{marker}] {name:30s}  votes={votes}  majority={majority}  expected={pair['expected']}")

        state["cumulative_cost"] = cumulative_cost
        save_state(state)

    print_summary(all_results, cumulative_cost)


if __name__ == "__main__":
    main()
