"""
test_multi_invoice.py — Test cases with multiple invoices per certificate.

Tests the system's ability to handle cases where a certificate references
multiple invoices (each as a separate PDF file).

Test data: Testdata/Testsystem med flera fakturor/
Each subfolder contains 1 certificate (SEG-*.pdf) + 2-3 invoice PDFs.

Estimated cost: ~$1.04-1.30
   (8 test cases × ~$0.13-0.16/case, slightly higher due to multiple PDFs)

Results saved to: MultiInvoiceResults/
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
TESTSYSTEM_DIR  = BASE_DIR / "Testdata" / "Testsystem med flera fakturor"
RESULTS_DIR     = BASE_DIR / "MultiInvoiceResults"
PROMPT_FILE     = BASE_DIR / "api_prompt_54.md"
SCHEMA_FILE     = BASE_DIR / "schema_slim_strict.json"
STATE_FILE      = BASE_DIR / "multi_invoice_state.json"

RESULTS_DIR.mkdir(exist_ok=True)

MODEL            = "gpt-5.4"
REASONING_EFFORT = "medium"
INPUT_PRICE      = 1.875   # $/1M tokens (Batch API = 50% off)
OUTPUT_PRICE     = 7.50
COST_LIMIT_USD   = 10.0
POLL_INTERVAL    = 30

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


def discover_cases() -> list[dict]:
    """Discover multi-invoice test cases from folder structure."""
    cases = []
    for folder in sorted(TESTSYSTEM_DIR.iterdir()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue

        # Parse folder name: MATCH_SEG-26D-465257 or MISMATCH_SEG-24D-118957
        parts = folder.name.split("_", 1)
        if len(parts) != 2:
            print(f"  WARNING: skipping folder with unexpected name: {folder.name}")
            continue

        category = parts[0]  # MATCH or MISMATCH
        cert_ref = parts[1]  # SEG-26D-465257

        if category not in ("MATCH", "MISMATCH"):
            print(f"  WARNING: skipping folder with unexpected category: {folder.name}")
            continue

        # Find certificate and invoice files
        cert_file = None
        invoice_files = []
        for pdf in sorted(folder.glob("*.pdf")):
            # Certificate starts with SEG- or contains cert_ref
            if pdf.stem.startswith("SEG-") or cert_ref in pdf.stem:
                cert_file = pdf
            else:
                invoice_files.append(pdf)

        # Also check .pdf.pdf files (some have double extension)
        for pdf in sorted(folder.glob("*.pdf.pdf")):
            if pdf.stem.replace(".pdf", "").startswith("SEG-") or cert_ref in pdf.name:
                cert_file = pdf
            else:
                invoice_files.append(pdf)

        if not cert_file:
            print(f"  WARNING: no certificate found in {folder.name}")
            continue
        if not invoice_files:
            print(f"  WARNING: no invoices found in {folder.name}")
            continue

        expected = "IDENTICAL" if category == "MATCH" else "NOT_IDENTICAL"
        cases.append({
            "name":          folder.name,
            "category":      category,
            "expected":      expected,
            "cert_file":     str(cert_file),
            "invoice_files": [str(f) for f in invoice_files],
            "num_invoices":  len(invoice_files),
        })

    return cases


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


def build_request(case: dict, file_ids: dict[str, str]) -> dict:
    """Build batch request — cert first, then all invoices."""
    content = [
        {"type": "file", "file": {"file_id": file_ids[case["cert_file"]]}}
    ]
    for inv_path in case["invoice_files"]:
        content.append({"type": "file", "file": {"file_id": file_ids[inv_path]}})

    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": content},
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
        "custom_id": case["name"],
        "method":    "POST",
        "url":       "/v1/chat/completions",
        "body":      body,
    }


def submit_batch(cases: list[dict]) -> dict:
    all_paths = []
    for c in cases:
        all_paths.append(c["cert_file"])
        all_paths.extend(c["invoice_files"])
    all_paths = list(set(all_paths))

    print(f"  Uploading {len(all_paths)} PDFs...", flush=True)
    file_ids = upload_pdfs(all_paths)

    lines = [json.dumps(build_request(c, file_ids), ensure_ascii=False) for c in cases]
    jsonl_bytes = "\n".join(lines).encode("utf-8")
    print(f"  Submitting batch ({len(jsonl_bytes)/1024:.1f} KB, {len(cases)} cases)...", flush=True)

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
        "case_names": [c["name"] for c in cases],
        "file_ids":   file_ids,
        "done":       False,
    }


def collect_results(batch_obj, batch_state: dict, case_by_name: dict) -> list[dict]:
    if not getattr(batch_obj, "output_file_id", None):
        print(f"  No output — batch failed.", flush=True)
        return []

    output_text = api_call(client.files.content, batch_obj.output_file_id).text
    results = []
    for line in output_text.strip().splitlines():
        entry     = json.loads(line)
        custom_id = entry["custom_id"]
        case      = case_by_name.get(custom_id)
        if case is None:
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

        is_pass   = comparison_result == case["expected"]
        is_review = comparison_result == "MANUAL_REVIEW"
        status    = "PASS" if is_pass else ("REVIEW" if is_review else "FAIL")

        status_icon = "✓" if status == "PASS" else ("?" if status == "REVIEW" else "✗")
        print(f"  {status_icon} {custom_id:35s} {status:6s}  got={comparison_result:16s}  exp={case['expected']:16s}  conf={conf}  invoices={case['num_invoices']}", flush=True)

        results.append({
            "name":          custom_id,
            "category":      case["category"],
            "expected":      case["expected"],
            "actual":        comparison_result,
            "status":        status,
            "confidence":    conf,
            "num_invoices":  case["num_invoices"],
            "input_tokens":  tok_in,
            "output_tokens": tok_out,
        })

        result["_meta"] = {
            "tested_at":     datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "prompt_hash":   prompt_hash,
            "model":         MODEL,
            "case":          custom_id,
            "expected":      case["expected"],
            "actual":        comparison_result,
            "status":        status,
            "num_invoices":  case["num_invoices"],
            "invoice_files": [Path(f).name for f in case["invoice_files"]],
            "cert_file":     Path(case["cert_file"]).name,
            "test_type":     "multi_invoice",
        }
        out_path = RESULTS_DIR / f"{custom_id}.json"
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    return results


def main():
    cases = discover_cases()
    if not cases:
        print("No test cases found.")
        return

    case_by_name = {c["name"]: c for c in cases}
    total_pdfs = sum(1 + c["num_invoices"] for c in cases)

    print(f"test_multi_invoice — model={MODEL}  effort={REASONING_EFFORT}  prompt_hash={prompt_hash}")
    print(f"{len(cases)} test cases ({total_pdfs} PDFs total):")
    for c in cases:
        print(f"  {c['name']:35s}  {c['category']:10s}  {c['num_invoices']} invoices")
    print(f"Results → {RESULTS_DIR.name}/")
    print()

    state = load_state()
    if state and state.get("prompt_hash") != prompt_hash:
        print("Prompt changed — starting fresh.")
        state = None

    if state and state.get("done"):
        print("Already completed. Delete multi_invoice_state.json to re-run.")
        return

    if state and state.get("batch_id") and not state.get("done"):
        batch_state = state
        print(f"Resuming batch {batch_state['batch_id']}...", flush=True)
    else:
        batch_state = submit_batch(cases)
        state = {**batch_state, "prompt_hash": prompt_hash, "cumulative_cost": 0.0}
        save_state(state)

    print(f"\nPolling until done...\n", flush=True)

    while True:
        time.sleep(POLL_INTERVAL)
        batch_obj = api_call(client.batches.retrieve, batch_state["batch_id"])
        counts = batch_obj.request_counts
        print(f"  Status: {batch_obj.status}  {counts.completed if counts else '?'}/{counts.total if counts else '?'}", flush=True)

        if batch_obj.status in ("completed", "failed", "expired", "cancelled"):
            results = collect_results(batch_obj, batch_state, case_by_name)
            delete_files(batch_state["file_ids"])

            total_cost = sum(cost_usd(r.get("input_tokens", 0), r.get("output_tokens", 0)) for r in results)
            state["done"] = True
            state["cumulative_cost"] = total_cost
            save_state(state)

            # --- Summary ---
            passed  = sum(1 for r in results if r.get("status") == "PASS")
            review  = sum(1 for r in results if r.get("actual") == "MANUAL_REVIEW")
            failed  = len(results) - passed - review
            errors  = sum(1 for r in results if "error" in r)

            print(f"\n{'='*75}")
            print(f"  MULTI-INVOICE TEST — {MODEL} — {len(results)} cases")
            print(f"  Prompt hash: {prompt_hash}")
            print(f"  {'─'*71}")
            print(f"  PASS: {passed}   REVIEW: {review}   FAIL: {failed}   ERRORS: {errors}")
            print(f"  {'─'*71}")

            for r in sorted(results, key=lambda x: x.get("name", "")):
                if "error" in r:
                    print(f"    ✗ {r['name']:35s}  ERROR: {r['error']}")
                    continue
                icon = "✓" if r["status"] == "PASS" else ("?" if r["actual"] == "MANUAL_REVIEW" else "✗")
                print(f"    {icon} {r['name']:35s}  {r['status']:6s}  got={r['actual']:16s}  exp={r['expected']:16s}  conf={r['confidence']}  inv={r['num_invoices']}")

            total_in  = sum(r.get("input_tokens", 0) for r in results)
            total_out = sum(r.get("output_tokens", 0) for r in results)
            avg_cost = total_cost / len(results) if results else 0
            print(f"\n  TOKENS & COST:")
            print(f"    Input tokens:       {total_in:,}")
            print(f"    Output tokens:      {total_out:,}")
            print(f"    Total cost:         ${total_cost:.4f}")
            print(f"    Avg cost per case:  ${avg_cost:.4f}")
            print(f"{'='*75}")
            return


if __name__ == "__main__":
    main()
