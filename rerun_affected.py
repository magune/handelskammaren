"""
rerun_affected.py — Targeted rerun of pairs affected by prompt fixes.

Tests ONLY the 11 false-approval pairs (model said IDENTICAL, should be NOT_IDENTICAL)
plus 3 mislabeled pairs (to confirm they still pass) = 14 pairs total.

Uses the UPDATED api_prompt_54.md with fixes:
  - 4.1.0.1: Shared brand prefix not sufficient for entity match
  - 4.1.0.2: Country must match for entity match
  - 4.3.3.4: Material/specification qualifiers are identity-bearing
  - 4.4.5.5.2: Quantity summation requires uniform product type

Results saved to: RerunAffectedResults/
State file:       rerun_affected_state.json
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
RESULTS_DIR     = BASE_DIR / "RerunAffectedResults"
PROMPT_FILE     = BASE_DIR / "api_prompt_54.md"
SCHEMA_FILE     = BASE_DIR / "schema_slim_strict.json"
STATE_FILE      = BASE_DIR / "rerun_affected_state.json"

RESULTS_DIR.mkdir(exist_ok=True)

MODEL            = "gpt-5.4"
REASONING_EFFORT = "medium"
INPUT_PRICE      = 1.875   # $/1M tokens (Batch API = 50% off)
OUTPUT_PRICE     = 7.50
COST_LIMIT_USD   = 10.0
CHUNK_SIZE       = 14      # All in one batch
POLL_INTERVAL    = 30

# --- Affected pairs ---
# Real mismatches the model missed (should be NOT_IDENTICAL):
FALSE_APPROVALS = [
    "P082_MISMATCH",
    "P097_MISMATCH",
    "P0143_MISMATCH",
    "P0144_MISMATCH",
    "P0148_MISMATCH",
    "P0152_MISMATCH",
    "P0153_MISMATCH",
    "P0175_MISMATCH",
    "P0191_MISMATCH",
    "P0194_MISMATCH",
    "P0195_MISMATCH",
]
# Mislabeled pairs (model was correct, should stay IDENTICAL — relabel candidates):
MISLABELED = [
    "P020_MISMATCH",
    "P031_MISMATCH",
    "P0180_MISMATCH",
]

TARGETED_PAIRS = set(FALSE_APPROVALS + MISLABELED)

client        = OpenAI()
system_prompt = PROMPT_FILE.read_text(encoding="utf-8")
prompt_hash   = hashlib.sha256(system_prompt.encode()).hexdigest()[:12]
schema        = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))


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


def discover_pairs() -> list[dict]:
    """Discover ONLY the targeted test pairs."""
    pair_files: dict[str, dict] = {}
    for pdf in sorted(TESTSYSTEM_DIR.glob("*.pdf")):
        parts = pdf.stem.split("_")
        if len(parts) < 3 or parts[1] not in ("MATCH", "MISMATCH") or parts[2] not in ("certificate", "invoice"):
            continue
        key = f"{parts[0]}_{parts[1]}"
        if key not in TARGETED_PAIRS:
            continue
        pair_files.setdefault(key, {})[parts[2]] = pdf

    pairs = []
    for key in sorted(pair_files):
        docs = pair_files[key]
        if "certificate" not in docs or "invoice" not in docs:
            print(f"  WARNING: incomplete pair {key}", flush=True)
            continue
        category = key.split("_")[1]
        pairs.append({
            "name":     key,
            "category": category,
            "expected": "IDENTICAL" if category == "MATCH" else "NOT_IDENTICAL",
            "files":    [str(docs["certificate"]), str(docs["invoice"])],
        })
    return pairs


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
    print(f"  Uploading {len(all_paths)} PDFs...", flush=True)
    file_ids = upload_pdfs(all_paths)

    lines = [json.dumps(build_request(p, file_ids), ensure_ascii=False) for p in chunk]
    jsonl_bytes = "\n".join(lines).encode("utf-8")
    print(f"  Submitting batch ({len(jsonl_bytes)/1024:.1f} KB, {len(chunk)} pairs)...", flush=True)

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
    print(f"  Batch submitted: {batch.id}", flush=True)
    return {
        "chunk_idx":  chunk_idx,
        "batch_id":   batch.id,
        "pair_names": [p["name"] for p in chunk],
        "file_ids":   file_ids,
        "done":       False,
    }


def collect_chunk(batch_obj, chunk_state: dict, pair_by_name: dict) -> list[dict]:
    if not getattr(batch_obj, "output_file_id", None):
        print(f"  No output — batch failed.", flush=True)
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

        overall           = result["overall_assessment"]
        comparison_result = overall["comparison_result"]

        # For mislabeled pairs, we expect the model to STILL say IDENTICAL
        # (which counts as FAIL against the test label, but is actually correct)
        is_mislabeled = custom_id in MISLABELED
        is_pass       = comparison_result == pair["expected"]
        is_review     = comparison_result == "MANUAL_REVIEW"
        status        = "PASS" if is_pass else ("REVIEW" if is_review else "FAIL")
        conf          = overall.get("confidence", "?")

        # Extra annotation for mislabeled pairs
        label = ""
        if is_mislabeled:
            if comparison_result == "IDENTICAL":
                label = " [MISLABELED — model correct]"
            elif comparison_result == "NOT_IDENTICAL":
                label = " [MISLABELED — model now disagrees]"

        status_icon = "✓" if status == "PASS" else ("?" if status == "REVIEW" else "✗")
        print(f"  {status_icon} {custom_id:25s} {status:6s}  got={comparison_result:14s}  conf={conf}{label}", flush=True)

        results.append({
            "name":          custom_id,
            "category":      pair["category"],
            "expected":      pair["expected"],
            "actual":        comparison_result,
            "status":        status,
            "confidence":    conf,
            "input_tokens":  tok_in,
            "output_tokens": tok_out,
            "is_mislabeled": is_mislabeled,
        })

        result["_meta"] = {
            "tested_at":     datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "prompt_hash":   prompt_hash,
            "model":         MODEL,
            "pair":          custom_id,
            "expected":      pair["expected"],
            "actual":        comparison_result,
            "status":        status,
            "is_mislabeled": is_mislabeled,
            "rerun":         "affected_pairs_prompt_fix",
        }
        out_path = RESULTS_DIR / f"{custom_id}_{pair['category']}.json"
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    return results


def main():
    pairs = discover_pairs()
    if not pairs:
        print("No pairs found.")
        return

    pair_by_name = {p["name"]: p for p in pairs}

    print(f"rerun_affected — model={MODEL}  effort={REASONING_EFFORT}  prompt_hash={prompt_hash}")
    print(f"{len(pairs)} targeted pairs ({len(FALSE_APPROVALS)} false approvals + {len(MISLABELED)} mislabeled)")
    print(f"Results → {RESULTS_DIR.name}/")
    print(f"Expected cost: ~${cost_usd(len(pairs)*36000, len(pairs)*4400):.2f}")
    print()

    found = set(p["name"] for p in pairs)
    missing = TARGETED_PAIRS - found
    if missing:
        print(f"  WARNING: {len(missing)} pairs not found: {missing}")

    state = load_state()
    if state and state.get("prompt_hash") != prompt_hash:
        print("Prompt changed — starting fresh.")
        state = None

    if state and state["chunks"] and state["chunks"][0].get("done"):
        print("Already completed. Delete rerun_affected_state.json to re-run.")
        return

    if state and state["chunks"] and not state["chunks"][0].get("done"):
        chunk_state = state["chunks"][0]
        print(f"Resuming batch {chunk_state['batch_id']}...", flush=True)
    else:
        chunk_state = submit_chunk(pairs, 0)
        state = {"prompt_hash": prompt_hash, "chunks": [chunk_state], "cumulative_cost": 0.0}
        save_state(state)

    print(f"\nPolling until done...\n", flush=True)

    while True:
        time.sleep(POLL_INTERVAL)
        batch_obj = api_call(client.batches.retrieve, chunk_state["batch_id"])
        counts = batch_obj.request_counts
        print(f"  Status: {batch_obj.status}  {counts.completed if counts else '?'}/{counts.total if counts else '?'}", flush=True)

        if batch_obj.status in ("completed", "failed", "expired", "cancelled"):
            results = collect_chunk(batch_obj, chunk_state, pair_by_name)
            delete_files(chunk_state["file_ids"])

            total_cost = sum(cost_usd(r.get("input_tokens", 0), r.get("output_tokens", 0)) for r in results)
            chunk_state["done"] = True
            state["cumulative_cost"] = total_cost
            save_state(state)

            # --- Summary ---
            print(f"\n{'='*65}")
            print(f"  RERUN RESULTS — {MODEL} — {len(results)} pairs")
            print(f"  Prompt hash: {prompt_hash}")
            print(f"  {'─'*61}")

            # False approvals: did the fix work?
            fa_results = [r for r in results if not r.get("is_mislabeled")]
            fa_fixed   = sum(1 for r in fa_results if r["actual"] == "NOT_IDENTICAL")
            fa_review  = sum(1 for r in fa_results if r["actual"] == "MANUAL_REVIEW")
            fa_still_wrong = sum(1 for r in fa_results if r["actual"] == "IDENTICAL")
            print(f"\n  FALSE APPROVALS ({len(fa_results)} pairs — should be NOT_IDENTICAL):")
            print(f"    Now NOT_IDENTICAL (FIXED):  {fa_fixed}")
            print(f"    Now MANUAL_REVIEW:          {fa_review}")
            print(f"    Still IDENTICAL (unfixed):   {fa_still_wrong}")
            for r in fa_results:
                icon = "✓" if r["actual"] == "NOT_IDENTICAL" else ("?" if r["actual"] == "MANUAL_REVIEW" else "✗")
                print(f"      {icon} {r['name']:25s} → {r['actual']}")

            # Mislabeled: did the model still get them right?
            ml_results = [r for r in results if r.get("is_mislabeled")]
            ml_still_correct = sum(1 for r in ml_results if r["actual"] == "IDENTICAL")
            print(f"\n  MISLABELED ({len(ml_results)} pairs — model should still say IDENTICAL):")
            print(f"    Still IDENTICAL (good):      {ml_still_correct}")
            print(f"    Changed verdict (regression):{len(ml_results) - ml_still_correct}")
            for r in ml_results:
                icon = "✓" if r["actual"] == "IDENTICAL" else "✗"
                print(f"      {icon} {r['name']:25s} → {r['actual']}")

            print(f"\n  Cost: ${total_cost:.4f}")
            print(f"{'='*65}")
            return


if __name__ == "__main__":
    main()
