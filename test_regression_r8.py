"""
test_regression_r8.py — Regression test for R8 prompt changes.

Runs a subset of the 242 pairs to verify that R8 changes (multi-invoice rules,
decimal separator normalization, article number MATCH, preposition tolerance,
logo/branding consignor, OCR readability, packlist acceptance) haven't broken
anything.

20 pairs selected across risk categories:
  - 6 Ship-To/Dealer consignee pairs (highest blast radius)
  - 3 Article number pairs
  - 3 Consignor branding/logo pairs
  - 3 Quantity decimal separator pairs
  - 5 Baseline sanity check (random PASS pairs)

Estimated cost: ~$2.60
   (20 pairs × ~$0.13/pair)

Results saved to: RegressionR8Results/
Baseline comparison from: Fullrun54Results/ + RerunPromptFixResults/
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
RESULTS_DIR     = BASE_DIR / "RegressionR8Results"
BASELINE_DIRS   = [
    BASE_DIR / "RerunPromptFixResults",  # Check here first (latest)
    BASE_DIR / "Fullrun54Results",       # Fallback
]
PROMPT_FILE     = BASE_DIR / "api_prompt_54.md"
SCHEMA_FILE     = BASE_DIR / "schema_slim_strict.json"
STATE_FILE      = BASE_DIR / "regression_r8_state.json"

RESULTS_DIR.mkdir(exist_ok=True)

MODEL            = "gpt-5.4"
REASONING_EFFORT = "medium"
INPUT_PRICE      = 1.875   # $/1M tokens (Batch API = 50% off)
OUTPUT_PRICE     = 7.50
POLL_INTERVAL    = 30

# --- Regression test pairs ---

# Ship-To/Dealer consignee (highest risk from 8.5.0.1 and 4.2.0.2 changes)
SHIP_TO_PAIRS = [
    "P082_MISMATCH",   # R6-fixed: Bill-To Aurobay ≠ cert Volvo Car Engine → REVIEW
    "P0148_MISMATCH",  # R6-fixed: Bill-To Meelunie B.V. ≠ cert Meelunie America → REVIEW
    "P0191_MISMATCH",  # R7-fixed: Consignee/deliveryaddress bypass → REVIEW
    "P0107_MATCH",     # PASS — Ship-To logic, should stay IDENTICAL
    "P0124_MATCH",     # PASS — Ship-To logic, should stay IDENTICAL
    "P023_MATCH",      # PASS — Ship-To logic, should stay IDENTICAL
]

# Article number rule 4.3.2.3 (changed from MANUAL_REVIEW to MATCH)
ARTICLE_NR_PAIRS = [
    "P201_MATCH",      # Target: was REVIEW, should become PASS with new rule
    "P214_MATCH",      # PASS — article number logic, should stay IDENTICAL
    "P0113_MISMATCH",  # PASS — should stay NOT_IDENTICAL
]

# Consignor branding/logo (new rule 4.1.1.1)
BRANDING_PAIRS = [
    "P018_MATCH",      # Target: was REVIEW (ERICSSON vs ERICSSON AB), should become PASS
    "P006_MATCH",      # PASS — branding match, should stay IDENTICAL
    "P034_MATCH",      # PASS — branding match, should stay IDENTICAL
]

# Quantity decimal separator (new rule 4.4.3.4)
DECIMAL_PAIRS = [
    "P031_MISMATCH",   # Target: was REVIEW (7801.920 vs 7.801,920), should improve
    "P027_MATCH",      # PASS — decimal formatting, should stay IDENTICAL
    "P058_MATCH",      # PASS — decimal formatting, should stay IDENTICAL
]

# Baseline sanity check (random PASS pairs, no rule changes target them)
BASELINE_PAIRS = [
    "P009_MATCH",      # PASS — should stay IDENTICAL
    "P017_MATCH",      # PASS — should stay IDENTICAL
    "P0142_MATCH",     # PASS — should stay IDENTICAL
    "P0178_MATCH",     # PASS — should stay IDENTICAL
    "P239_MATCH",      # PASS — should stay IDENTICAL
]

ALL_PAIRS = set(
    SHIP_TO_PAIRS + ARTICLE_NR_PAIRS + BRANDING_PAIRS +
    DECIMAL_PAIRS + BASELINE_PAIRS
)

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


def load_baseline(pair_name: str, category: str):
    """Load baseline result, preferring RerunPromptFixResults."""
    for bdir in BASELINE_DIRS:
        path = bdir / f"{pair_name}_{category}.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                meta = data.get("_meta", {})
                overall = data.get("overall_assessment", {})
                return {
                    "actual": meta.get("actual", overall.get("comparison_result", "?")),
                    "status": meta.get("status", "?"),
                    "confidence": overall.get("confidence", "?"),
                    "source": bdir.name,
                }
            except Exception:
                continue
    return None


def get_pair_type(pair_name: str) -> str:
    if pair_name in set(SHIP_TO_PAIRS):
        return "ship_to"
    elif pair_name in set(ARTICLE_NR_PAIRS):
        return "article_nr"
    elif pair_name in set(BRANDING_PAIRS):
        return "branding"
    elif pair_name in set(DECIMAL_PAIRS):
        return "decimal"
    else:
        return "baseline"


def discover_pairs() -> list[dict]:
    pair_files: dict[str, dict] = {}
    for pdf in sorted(TESTSYSTEM_DIR.glob("*.pdf")):
        parts = pdf.stem.split("_")
        if len(parts) < 3 or parts[1] not in ("MATCH", "MISMATCH") or parts[2] not in ("certificate", "invoice"):
            continue
        key = f"{parts[0]}_{parts[1]}"
        if key not in ALL_PAIRS:
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


def submit_batch(pairs: list[dict]) -> dict:
    all_paths = list({f for p in pairs for f in p["files"]})
    print(f"  Uploading {len(all_paths)} PDFs...", flush=True)
    file_ids = upload_pdfs(all_paths)

    lines = [json.dumps(build_request(p, file_ids), ensure_ascii=False) for p in pairs]
    jsonl_bytes = "\n".join(lines).encode("utf-8")
    print(f"  Submitting batch ({len(jsonl_bytes)/1024:.1f} KB, {len(pairs)} pairs)...", flush=True)

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
        "batch_id":   batch.id,
        "pair_names": [p["name"] for p in pairs],
        "file_ids":   file_ids,
        "done":       False,
    }


def collect_results(batch_obj, batch_state: dict, pair_by_name: dict) -> list[dict]:
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
        conf              = overall.get("confidence", "?")

        is_pass   = comparison_result == pair["expected"]
        is_review = comparison_result == "MANUAL_REVIEW"
        status    = "PASS" if is_pass else ("REVIEW" if is_review else "FAIL")

        baseline = load_baseline(custom_id, pair["category"])
        pair_type = get_pair_type(custom_id)

        if baseline:
            if baseline["actual"] != comparison_result:
                change = f"  was={baseline['actual']}"
                if baseline["status"] == status:
                    change_type = "same_status"
                elif status == "PASS" and baseline["status"] != "PASS":
                    change_type = "IMPROVED"
                elif baseline["status"] == "PASS" and status != "PASS":
                    change_type = "REGRESSION"
                else:
                    change_type = "changed"
            else:
                change = "  (unchanged)"
                change_type = "unchanged"
        else:
            change = "  (no baseline)"
            change_type = "no_baseline"

        status_icon = "✓" if status == "PASS" else ("?" if status == "REVIEW" else "✗")
        regression_flag = " ⚠️REGRESSION" if change_type == "REGRESSION" else ""
        improved_flag = " ✨IMPROVED" if change_type == "IMPROVED" else ""
        print(f"  {status_icon} {custom_id:25s} {status:6s}  got={comparison_result:16s}  [{pair_type:10s}]{change}{regression_flag}{improved_flag}", flush=True)

        results.append({
            "name":          custom_id,
            "category":      pair["category"],
            "expected":      pair["expected"],
            "actual":        comparison_result,
            "status":        status,
            "confidence":    conf,
            "pair_type":     pair_type,
            "change_type":   change_type,
            "baseline":      baseline,
            "input_tokens":  tok_in,
            "output_tokens": tok_out,
        })

        result["_meta"] = {
            "tested_at":     datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "prompt_hash":   prompt_hash,
            "model":         MODEL,
            "pair":          custom_id,
            "expected":      pair["expected"],
            "actual":        comparison_result,
            "status":        status,
            "rerun":         "regression_r8",
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

    print(f"test_regression_r8 — model={MODEL}  effort={REASONING_EFFORT}  prompt_hash={prompt_hash}")
    print(f"{len(pairs)} regression test pairs:")
    for ptype, label in [
        ("ship_to",     "Ship-To/Dealer consignee"),
        ("article_nr",  "Article number 4.3.2.3"),
        ("branding",    "Consignor branding/logo"),
        ("decimal",     "Quantity decimal separator"),
        ("baseline",    "Baseline sanity check"),
    ]:
        count = sum(1 for p in pairs if get_pair_type(p["name"]) == ptype)
        if count:
            print(f"  {count} {label}")
    print(f"Results → {RESULTS_DIR.name}/")
    print(f"Expected cost: ~${cost_usd(len(pairs)*36000, len(pairs)*4400):.2f}")
    print()

    found = set(p["name"] for p in pairs)
    missing = ALL_PAIRS - found
    if missing:
        print(f"  WARNING: {len(missing)} pairs not found: {missing}")

    state = load_state()
    if state and state.get("prompt_hash") != prompt_hash:
        print("Prompt changed — starting fresh.")
        state = None

    if state and state.get("done"):
        print("Already completed. Delete regression_r8_state.json to re-run.")
        return

    if state and state.get("batch_id") and not state.get("done"):
        batch_state = state
        print(f"Resuming batch {batch_state['batch_id']}...", flush=True)
    else:
        batch_state = submit_batch(pairs)
        state = {**batch_state, "prompt_hash": prompt_hash, "cumulative_cost": 0.0}
        save_state(state)

    print(f"\nPolling until done...\n", flush=True)

    while True:
        time.sleep(POLL_INTERVAL)
        batch_obj = api_call(client.batches.retrieve, batch_state["batch_id"])
        counts = batch_obj.request_counts
        print(f"  Status: {batch_obj.status}  {counts.completed if counts else '?'}/{counts.total if counts else '?'}", flush=True)

        if batch_obj.status in ("completed", "failed", "expired", "cancelled"):
            results = collect_results(batch_obj, batch_state, pair_by_name)
            delete_files(batch_state["file_ids"])

            total_cost = sum(cost_usd(r.get("input_tokens", 0), r.get("output_tokens", 0)) for r in results)
            state["done"] = True
            state["cumulative_cost"] = total_cost
            save_state(state)

            # --- Summary ---
            regressions = [r for r in results if r.get("change_type") == "REGRESSION"]
            improvements = [r for r in results if r.get("change_type") == "IMPROVED"]
            unchanged = [r for r in results if r.get("change_type") == "unchanged"]
            changed = [r for r in results if r.get("change_type") == "changed"]

            print(f"\n{'='*75}")
            print(f"  REGRESSION TEST R8 — {MODEL} — {len(results)} pairs")
            print(f"  Prompt hash: {prompt_hash}")
            print(f"  {'─'*71}")

            for ptype, label in [
                ("ship_to",     "SHIP-TO/DEALER CONSIGNEE"),
                ("article_nr",  "ARTICLE NUMBER 4.3.2.3"),
                ("branding",    "CONSIGNOR BRANDING/LOGO"),
                ("decimal",     "QUANTITY DECIMAL SEPARATOR"),
                ("baseline",    "BASELINE SANITY CHECK"),
            ]:
                group = [r for r in results if r.get("pair_type") == ptype]
                if not group:
                    continue
                passed = sum(1 for r in group if r["status"] == "PASS")
                review = sum(1 for r in group if r["actual"] == "MANUAL_REVIEW")
                failed = len(group) - passed - review
                print(f"\n  {label} ({len(group)} pairs):  PASS={passed}  REVIEW={review}  FAIL={failed}")
                for r in sorted(group, key=lambda x: x["name"]):
                    icon = "✓" if r["status"] == "PASS" else ("?" if r["actual"] == "MANUAL_REVIEW" else "✗")
                    base = r.get("baseline", {})
                    was = f"  (was {base['actual']})" if base and base["actual"] != r["actual"] else ""
                    flag = " ⚠️REGRESSION" if r.get("change_type") == "REGRESSION" else ""
                    flag += " ✨IMPROVED" if r.get("change_type") == "IMPROVED" else ""
                    print(f"      {icon} {r['name']:25s} → {r['actual']:16s} exp={r['expected']:16s} conf={r['confidence']}{was}{flag}")

            print(f"\n  {'─'*71}")
            print(f"  REGRESSIONS: {len(regressions)}")
            for r in regressions:
                print(f"    ⚠️  {r['name']:25s} {r.get('baseline',{}).get('status','?')} → {r['status']}  (was {r.get('baseline',{}).get('actual','?')} → {r['actual']})")
            if not regressions:
                print(f"    None — all clear! ✓")

            print(f"  IMPROVEMENTS: {len(improvements)}")
            for r in improvements:
                print(f"    ✨ {r['name']:25s} {r.get('baseline',{}).get('status','?')} → {r['status']}  (was {r.get('baseline',{}).get('actual','?')} → {r['actual']})")

            print(f"  UNCHANGED: {len(unchanged)}")
            print(f"  OTHER CHANGES: {len(changed)}")

            total_in  = sum(r.get("input_tokens", 0) for r in results)
            total_out = sum(r.get("output_tokens", 0) for r in results)
            avg_cost = total_cost / len(results) if results else 0
            print(f"\n  TOKENS & COST:")
            print(f"    Input tokens:       {total_in:,}")
            print(f"    Output tokens:      {total_out:,}")
            print(f"    Total cost:         ${total_cost:.4f}")
            print(f"    Avg cost per pair:  ${avg_cost:.4f}")
            print(f"{'='*75}")
            return


if __name__ == "__main__":
    main()
