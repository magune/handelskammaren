"""
model_comparison_test.py — Compare model/config options on same 10 pairs.

Runs the same document pairs through multiple configurations simultaneously
using the OpenAI Batch API, then produces a side-by-side accuracy + cost report.

Configurations tested:
  A  gpt-5.4 / medium  (baseline)
  B  gpt-4.1
  C  gpt-4.1-mini

Usage:
  python3 model_comparison_test.py

Results saved to: ModelComparisonResults/
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
RESULTS_DIR     = BASE_DIR / "ModelComparisonResults"
PROMPT_FILE     = BASE_DIR / "api_prompt.md"
SCHEMA_FILE     = BASE_DIR / "schema_slim_strict.json"
STATE_FILE      = BASE_DIR / "model_comparison_state.json"

RESULTS_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Configurations to compare
# ---------------------------------------------------------------------------
# Pricing per 1M tokens (Batch API ~50% off list price)
CONFIGS = [
    {
        "id": "A",
        "label": "5.4/med",
        "model": "gpt-5.4",
        "reasoning_effort": "medium",
        "input_price":  3.75,
        "output_price": 15.0,
    },
    {
        "id": "B",
        "label": "4.1",
        "model": "gpt-4.1",
        "reasoning_effort": None,
        "input_price":  1.0,
        "output_price": 2.0,
    },
    {
        "id": "C",
        "label": "4.1-mini",
        "model": "gpt-4.1-mini",
        "reasoning_effort": None,
        "input_price":  0.05,
        "output_price": 0.2,
    },
]

# ---------------------------------------------------------------------------
# Test pairs — same 10 used for gpt-4.1 accuracy test, covering all rule areas
# ---------------------------------------------------------------------------
TEST_PAIRS = [
    "P001",    # IDENTICAL, enkel — basfall
    "P003",    # NOT_IDENTICAL — tydlig MISMATCH
    "P005",    # NOT_IDENTICAL — consignee mismatch
    "P008",    # IDENTICAL — EU-normalisering origin
    "P019",    # IDENTICAL — HK/China-normalisering
    "P072",    # IDENTICAL — summering rader + EU origin
    "P087",    # IDENTICAL — artikelnummer-matchning
    "P0103",   # NOT_IDENTICAL — fakturareferens + origin mismatch
    "P0118",   # IDENTICAL — fullständig verifiering
    "P231",    # NOT_IDENTICAL — hög konfidens mismatch
]

POLL_INTERVAL   = 30
RETRY_BASE      = 15
RETRY_MAX       = 300

client        = OpenAI()
system_prompt = PROMPT_FILE.read_text(encoding="utf-8")
prompt_hash   = hashlib.sha256(system_prompt.encode()).hexdigest()[:12]
schema        = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def api_call(func, *args, **kwargs):
    delay = RETRY_BASE
    attempt = 0
    while True:
        try:
            return func(*args, **kwargs)
        except (APIConnectionError, APITimeoutError) as e:
            attempt += 1
            print(f"  [network error #{attempt}] {e} — retrying in {delay}s...")
            time.sleep(delay)
            delay = min(delay * 2, RETRY_MAX)
        except Exception:
            raise


def discover_pairs() -> dict[str, dict]:
    """Return {pair_id: {name, expected, files}} for TEST_PAIRS."""
    pair_files: dict[str, dict] = {}
    for pdf in sorted(TESTSYSTEM_DIR.glob("*.pdf")):
        parts = pdf.stem.split("_")
        if len(parts) < 3 or parts[1] not in ("MATCH", "MISMATCH") or parts[2] not in ("certificate", "invoice"):
            continue
        pair_id   = parts[0]
        pair_key  = f"{parts[0]}_{parts[1]}"
        pair_files.setdefault(pair_id, {"key": pair_key, "category": parts[1], "files": {}})[
            "files"
        ][parts[2]] = pdf

    pairs = {}
    for pid in TEST_PAIRS:
        info = pair_files.get(pid)
        if not info or "certificate" not in info["files"] or "invoice" not in info["files"]:
            print(f"WARNING: pair {pid} not found or incomplete, skipping")
            continue
        pairs[pid] = {
            "name":     info["key"],
            "pair_id":  pid,
            "category": info["category"],
            "expected": "IDENTICAL" if info["category"] == "MATCH" else "NOT_IDENTICAL",
            "files":    [str(info["files"]["certificate"]), str(info["files"]["invoice"])],
        }
    return pairs


def upload_pdfs(paths: list[str]) -> dict[str, str]:
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


def build_request(pair: dict, file_ids: dict[str, str], config: dict) -> dict:
    user_message = [
        {"type": "file", "file": {"file_id": file_ids[f]}}
        for f in pair["files"]
    ]
    body: dict = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name":   "verification_output",
                "strict": True,
                "schema": schema,
            },
        },
    }
    if config.get("reasoning_effort"):
        body["reasoning_effort"] = config["reasoning_effort"]
    return {
        "custom_id": pair["pair_id"],
        "method":    "POST",
        "url":       "/v1/chat/completions",
        "body":      body,
    }


def submit_batch(pairs: list[dict], file_ids: dict[str, str], config: dict) -> str:
    """Build and submit one batch for a config. Returns batch_id."""
    lines       = [json.dumps(build_request(p, file_ids, config), ensure_ascii=False) for p in pairs]
    jsonl_bytes = "\n".join(lines).encode("utf-8")
    label       = config["label"]
    print(f"  [{label}] Submitting batch ({len(jsonl_bytes)/1024:.1f} KB)...", flush=True)
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
    print(f"  [{label}] Batch submitted: {batch.id}")
    return batch.id


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return None


def collect_batch(batch_id: str, config: dict, pairs_by_id: dict[str, dict]) -> list[dict]:
    """Download results for a completed batch and return list of result dicts."""
    batch_obj = api_call(client.batches.retrieve, batch_id)
    if not getattr(batch_obj, "output_file_id", None):
        print(f"  [{config['label']}] No output file.")
        if getattr(batch_obj, "error_file_id", None):
            errors = api_call(client.files.content, batch_obj.error_file_id).text
            for line in errors.strip().splitlines()[:5]:
                print(f"    {line}")
        return []

    output_text = api_call(client.files.content, batch_obj.output_file_id).text
    results = []
    for line in output_text.strip().splitlines():
        entry     = json.loads(line)
        pair_id   = entry["custom_id"]
        pair      = pairs_by_id.get(pair_id)
        error     = entry.get("error")
        resp_body = entry.get("response", {}).get("body", {})

        if error or not resp_body:
            results.append({"pair_id": pair_id, "config_id": config["id"], "error": str(error)})
            continue

        result  = json.loads(resp_body["choices"][0]["message"]["content"])
        usage   = resp_body.get("usage", {})
        inp_tok = usage.get("prompt_tokens", 0)
        out_tok = usage.get("completion_tokens", 0)
        cost    = (inp_tok * config["input_price"] + out_tok * config["output_price"]) / 1_000_000

        actual   = result["overall_assessment"]["comparison_result"]
        expected = pair["expected"]
        is_pass  = actual == expected
        is_review = actual == "MANUAL_REVIEW"
        status   = "PASS" if is_pass else ("REVIEW" if is_review else "FAIL")

        # Save individual result file
        result["_meta"] = {
            "config_id":    config["id"],
            "config_label": config["label"],
            "pair_id":      pair_id,
            "expected":     expected,
            "actual":       actual,
            "status":       status,
            "prompt_hash":  prompt_hash,
            "tested_at":    datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "input_tokens": inp_tok,
            "output_tokens": out_tok,
            "cost_usd":     round(cost, 5),
        }
        out_file = RESULTS_DIR / f"{pair_id}_{pair['category']}_config{config['id']}.json"
        out_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

        results.append({
            "pair_id":    pair_id,
            "config_id":  config["id"],
            "expected":   expected,
            "actual":     actual,
            "status":     status,
            "inp_tok":    inp_tok,
            "out_tok":    out_tok,
            "cost":       cost,
            "triggers":   result["overall_assessment"].get("manual_review_triggers", []),
        })
    return results


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_report(all_results: list[dict], pairs_by_id: dict[str, dict]):
    configs_by_id = {c["id"]: c for c in CONFIGS}
    results_by_config: dict[str, list] = {c["id"]: [] for c in CONFIGS}
    for r in all_results:
        results_by_config[r["config_id"]].append(r)

    print(f"\n{'='*72}")
    print(f"  MODEL COMPARISON REPORT — prompt hash {prompt_hash}")
    print(f"  {len(TEST_PAIRS)} pairs × {len(CONFIGS)} configs")
    print(f"{'='*72}")

    # Per-config summary
    for cfg in CONFIGS:
        cid     = cfg["id"]
        label   = cfg["label"]
        res     = results_by_config[cid]
        n       = len(res)
        if n == 0:
            print(f"\n  Config {cid} ({label}): no results")
            continue
        passes  = sum(1 for r in res if r["status"] == "PASS")
        reviews = sum(1 for r in res if r["status"] == "REVIEW")
        fails   = sum(1 for r in res if r["status"] == "FAIL")
        errors  = sum(1 for r in res if "error" in r)
        total_cost = sum(r.get("cost", 0) for r in res)
        avg_cost   = total_cost / n if n else 0
        proj_242   = avg_cost * 242
        proj_1000d = avg_cost * 1000 * 30

        print(f"\n  ── Config {cid}: {label} ──")
        print(f"     PASS:   {passes}/{n}  ({passes/n*100:.0f}%)")
        print(f"     REVIEW: {reviews}/{n}  ({reviews/n*100:.0f}%)")
        print(f"     FAIL:   {fails}/{n}  ({fails/n*100:.0f}%)")
        if errors:
            print(f"     ERROR:  {errors}/{n}")
        print(f"     Cost/pair:     ~${avg_cost:.3f}")
        print(f"     Cost/242 pairs: ~${proj_242:.1f}")
        print(f"     Cost/1000/day × 30 days: ~${proj_1000d:.0f}/month")

    # Side-by-side per pair
    print(f"\n{'─'*72}")
    print(f"  PAIR-BY-PAIR COMPARISON")
    print(f"{'─'*72}")
    header = f"  {'Pair':<10} {'Expected':<14}"
    for cfg in CONFIGS:
        header += f"  {cfg['id']}:{cfg['label']:<22}"
    print(header)
    print(f"  {'─'*70}")

    for pid in TEST_PAIRS:
        pair = pairs_by_id.get(pid)
        if not pair:
            continue
        line = f"  {pid:<10} {pair['expected']:<14}"
        for cfg in CONFIGS:
            r = next((x for x in results_by_config[cfg["id"]] if x["pair_id"] == pid), None)
            if r is None:
                cell = f"{'—':<26}"
            elif "error" in r:
                cell = f"{'ERROR':<12} ${r.get('cost',0):.3f}    "
            else:
                status_str = f"{r['status']}/{r['actual'][:6]}"
                cell = f"{status_str:<18} ${r.get('cost',0):.3f}  "
            line += f"  {cell}"
        print(line)

    # FAILs detail
    fails = [r for r in all_results if r.get("status") == "FAIL"]
    if fails:
        print(f"\n{'─'*72}")
        print(f"  FAILS DETAIL")
        for r in fails:
            cfg_label = configs_by_id[r["config_id"]]["label"]
            print(f"  FAIL  {r['pair_id']}  config={cfg_label}  expected={r['expected']}  got={r['actual']}")

    print(f"\n{'='*72}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"\nModel comparison test — prompt hash {prompt_hash}")
    print(f"Configs: {', '.join(c['label'] for c in CONFIGS)}")
    print(f"Pairs:   {', '.join(TEST_PAIRS)}\n")

    pairs_by_id = discover_pairs()
    if not pairs_by_id:
        print("ERROR: no test pairs found")
        return

    pairs = list(pairs_by_id.values())

    # Resume or start fresh
    state = load_state()
    all_results: list[dict] = []

    if state and state.get("prompt_hash") == prompt_hash:
        print("Resuming from saved state...")
        all_results = state.get("results", [])
        pending = state.get("pending_batches", [])
    else:
        if state:
            print("Prompt changed — starting fresh.")

        all_paths = list({f for p in pairs for f in p["files"]})

        print(f"\nUploading {len(all_paths)} PDFs...")
        file_ids_map = upload_pdfs(all_paths)

        # Submit one batch per config
        pending = []
        for cfg in CONFIGS:
            batch_id = submit_batch(pairs, file_ids_map, cfg)
            pending.append({"config_id": cfg["id"], "batch_id": batch_id})

        all_file_ids = file_ids_map

        state = {
            "prompt_hash":      prompt_hash,
            "pending_batches":  pending,
            "results":          [],
            "file_ids":         all_file_ids,
        }
        save_state(state)
        print()

    # Poll until all batches done
    file_ids = state.get("file_ids", {})
    configs_by_id = {c["id"]: c for c in CONFIGS}

    def print_live_status(all_results, pending_ids):
        """Print compact live table after each poll cycle."""
        results_by_config = {c["id"]: [] for c in CONFIGS}
        for r in all_results:
            results_by_config[r["config_id"]].append(r)

        print(f"\n  ┌─ LIVE STATUS ({'─'*38})")
        for cfg in CONFIGS:
            cid   = cfg["id"]
            res   = results_by_config[cid]
            n     = len(res)
            if cid in pending_ids:
                state_str = "waiting..."
            elif n == 0:
                state_str = "no results"
            else:
                passes  = sum(1 for r in res if r["status"] == "PASS")
                reviews = sum(1 for r in res if r["status"] == "REVIEW")
                fails   = sum(1 for r in res if r["status"] == "FAIL")
                avg_cost = sum(r.get("cost", 0) for r in res) / n
                state_str = (f"PASS={passes} REVIEW={reviews} FAIL={fails}  "
                             f"~${avg_cost:.3f}/pair")
            print(f"  │  {cfg['label']:<22} {state_str}")
        print(f"  └{'─'*50}")

    while pending:
        still_pending = []
        newly_completed = []
        for batch_state in pending:
            cid      = batch_state["config_id"]
            batch_id = batch_state["batch_id"]
            cfg      = configs_by_id[cid]
            try:
                batch_obj = api_call(client.batches.retrieve, batch_id)
            except Exception as e:
                print(f"  Could not retrieve {batch_id}: {e}")
                still_pending.append(batch_state)
                continue

            status = batch_obj.status

            if status == "completed":
                results = collect_batch(batch_id, cfg, pairs_by_id)
                all_results.extend(results)
                newly_completed.append(cfg["label"])
                state["results"] = all_results
                state["pending_batches"] = [b for b in pending if b["batch_id"] != batch_id]
                save_state(state)
            elif status in ("failed", "expired", "cancelled"):
                print(f"  [{cfg['label']}] Batch {status} — skipping")
            else:
                still_pending.append(batch_state)

        pending = still_pending
        pending_ids = {b["config_id"] for b in pending}

        if newly_completed:
            print(f"\n  ✓ Completed: {', '.join(newly_completed)}")

        print_live_status(all_results, pending_ids)

        if pending:
            print(f"  Waiting {POLL_INTERVAL}s ({len(pending)} still running)...")
            time.sleep(POLL_INTERVAL)

    # Clean up uploaded PDFs
    if file_ids:
        print("\nCleaning up uploaded files...")
        delete_files(file_ids)

    # Delete state file on clean completion
    STATE_FILE.unlink(missing_ok=True)

    print_report(all_results, pairs_by_id)


if __name__ == "__main__":
    main()
