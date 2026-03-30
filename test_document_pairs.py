import json
import re
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

BASE_DIR = Path(__file__).parent
TESTDATA_DIR = BASE_DIR / "Testdata"
TESTSYSTEM_DIR = TESTDATA_DIR / "Testsystem företag"
TESTREPORTS_DIR = BASE_DIR / "Testreports"
PROMPT_FILE = BASE_DIR / "api_prompt.md"
SCHEMA_FILE = BASE_DIR / "schema_slim_strict.json"
BATCH_STATE_FILE = BASE_DIR / "batch_state.json"

# Set to None to run all pairs, or an integer to limit (e.g. 10)
MAX_PAIRS = None

# Max pairs per batch submission (keeps enqueued tokens under org limit)
BATCH_CHUNK_SIZE = 50

TESTREPORTS_DIR.mkdir(exist_ok=True)

client = OpenAI()

system_prompt = PROMPT_FILE.read_text(encoding="utf-8")
schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))


def get_document_pairs():
    """Discover all document pairs from Testsystem föreatg using P001_MATCH/MISMATCH_certificate/invoice.pdf naming."""
    if not TESTSYSTEM_DIR.exists():
        print(f"WARNING: {TESTSYSTEM_DIR} not found")
        return []

    # Group files by pair key: "{id}_{MATCH|MISMATCH}"
    pair_files: dict[str, dict[str, Path]] = {}
    for pdf in sorted(TESTSYSTEM_DIR.glob("*.pdf")):
        # Expected format: P001_MATCH_certificate.pdf or P001_MISMATCH_invoice.pdf
        parts = pdf.stem.split("_")  # e.g. ["P001", "MATCH", "certificate"]
        if len(parts) < 3 or parts[1] not in ("MATCH", "MISMATCH") or parts[2] not in ("certificate", "invoice"):
            print(f"WARNING: Unexpected filename format, skipping: {pdf.name}")
            continue
        pair_key = f"{parts[0]}_{parts[1]}"  # e.g. "P001_MATCH"
        doc_type = parts[2]  # "certificate" or "invoice"
        pair_files.setdefault(pair_key, {})[doc_type] = pdf

    pairs = []
    for pair_key in sorted(pair_files):
        docs = pair_files[pair_key]
        if "certificate" not in docs or "invoice" not in docs:
            print(f"WARNING: {pair_key} missing certificate or invoice, skipping")
            continue
        match_status = pair_key.split("_")[1]
        expected = "IDENTICAL" if match_status == "MATCH" else "NOT_IDENTICAL"
        pairs.append({
            "name": pair_key,
            "category": match_status,
            "expected": expected,
            "files": [docs["certificate"], docs["invoice"]],
        })

    return pairs


def upload_pdfs(pairs: list[dict]) -> dict[str, str]:
    """Upload all unique PDFs to OpenAI Files API. Returns {local_path_str: file_id}."""
    all_paths = {str(f) for p in pairs for f in p["files"]}
    file_ids = {}
    print(f"Uploading {len(all_paths)} PDF files to OpenAI...")
    for i, path_str in enumerate(sorted(all_paths), 1):
        path = Path(path_str)
        print(f"  [{i}/{len(all_paths)}] {path.name}", flush=True)
        with path.open("rb") as fh:
            uploaded = client.files.create(file=(path.name, fh, "application/pdf"), purpose="user_data")
        file_ids[path_str] = uploaded.id
    return file_ids


def delete_uploaded_files(file_ids: dict[str, str]):
    """Delete all previously uploaded files from OpenAI."""
    print(f"Cleaning up {len(file_ids)} uploaded files...")
    for file_id in file_ids.values():
        try:
            client.files.delete(file_id)
        except Exception:
            pass


def build_batch_request(pair: dict, file_ids: dict[str, str]) -> dict:
    """Build a single batch JSONL request for a document pair using pre-uploaded file IDs."""
    content = []
    for pdf_path in pair["files"]:
        content.append({
            "type": "file",
            "file": {"file_id": file_ids[str(pdf_path)]},
        })
    return {
        "custom_id": pair["name"],
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": "gpt-5.4",
            "temperature": 0,
            "seed": 42,
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


def submit_batch(pairs: list[dict]) -> str:
    """Upload PDFs, build JSONL, create a batch job, save state and return batch_id."""
    file_ids = upload_pdfs(pairs)

    print(f"Building batch with {len(pairs)} requests...")
    lines = [json.dumps(build_batch_request(p, file_ids), ensure_ascii=False) for p in pairs]
    jsonl_bytes = "\n".join(lines).encode("utf-8")
    print(f"Uploading batch input ({len(jsonl_bytes) / 1024:.1f} KB)...")

    uploaded = client.files.create(
        file=("batch_input.jsonl", jsonl_bytes, "application/jsonl"),
        purpose="batch",
    )
    batch = client.batches.create(
        input_file_id=uploaded.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
    )
    print(f"Batch submitted: {batch.id}")

    # Persist state so the collect phase can resume after restart
    state = {
        "batch_id": batch.id,
        "file_ids": file_ids,
        "pairs": [
            {
                "name": p["name"],
                "category": p["category"],
                "expected": p["expected"],
                "files": [str(f) for f in p["files"]],
            }
            for p in pairs
        ],
    }
    BATCH_STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    return batch.id


def poll_batch(batch_id: str):
    """Poll until the batch reaches a terminal state and return the batch object."""
    while True:
        batch = client.batches.retrieve(batch_id)
        counts = batch.request_counts
        completed = counts.completed if counts else "?"
        total = counts.total if counts else "?"
        print(f"  [{batch.status}]  {completed}/{total} completed", flush=True)
        if batch.status in ("completed", "failed", "expired", "cancelled"):
            return batch
        time.sleep(30)


def print_pair_result(pair: dict, result: dict, input_tokens: int, output_tokens: int) -> dict:
    """Print detailed output for one pair and return a summary dict."""
    name = pair["name"]
    file_names = [Path(f).name for f in pair["files"]]
    overall = result["overall_assessment"]
    comparison_result = overall["comparison_result"]

    is_pass = comparison_result == pair["expected"]
    is_manual_review = comparison_result == "MANUAL_REVIEW"
    if is_pass:
        status = "PASS"
    elif is_manual_review:
        status = "REVIEW"
    else:
        status = "FAIL"

    print(f"\n{'=' * 60}")
    print(f"  {name} ({pair['category']})")
    print(f"  File A: {file_names[0]}")
    print(f"  File B: {file_names[1]}")
    print(f"  Expected: {pair['expected']}")
    print(f"\n  Result: {comparison_result} — {status}")
    print(f"  Overall confidence: {overall.get('confidence', 'N/A')}")
    print(f"  Workflow: {overall.get('workflow_recommendation', 'N/A')}")
    if overall.get("decision_summary"):
        print(f"\n  Decision summary:")
        print(f"    {overall['decision_summary']}")

    # Print activated rules
    ra = result.get("rule_activation", {})
    active_flags = []
    for flag_key, flag_label in [
        ("lc_exception_active", "LC exception"),
        ("general_goods_description_with_invoice_reference_active", "General goods + invoice ref"),
        ("mixed_origins_rule_active", "Mixed origins"),
        ("to_order_rule_active", "To order"),
        ("eu_origin_normalization_active", "EU normalization"),
    ]:
        if ra.get(flag_key):
            active_flags.append(flag_label)
    if ra.get("quantity_exception_applied"):
        active_flags.append(f"Quantity exception {ra['quantity_exception_applied']}")
    if active_flags:
        print(f"\n  Active rules: {', '.join(active_flags)}")

    # Print detailed control point trace
    cp = result.get("control_points", {})
    cp_labels = {
        "consignor": "4.1 Consignor (Avsändare)",
        "consignee": "4.2 Consignee (Mottagare)",
        "goods_description": "4.3 Goods Description (Varubeskrivning)",
        "quantity": "4.4 Quantity (Kvantitet/Mängd)",
        "origin": "4.5 Origin (Ursprungsland)",
    }
    print(f"\n  {'─' * 56}")
    print(f"  CONTROL POINT TRACE")
    print(f"  {'─' * 56}")

    for cp_name, cp_label in cp_labels.items():
        point = cp.get(cp_name, {})
        cp_status = point.get("status", "N/A")
        cp_conf = point.get("confidence", "N/A")
        marker = "PASS" if cp_status == "MATCH" else "FAIL" if cp_status == "MISMATCH" else "SKIP" if cp_status == "NOT_APPLICABLE" else "WARN"
        conf_str = f"{cp_conf:.2f}" if isinstance(cp_conf, (int, float)) else str(cp_conf)

        print(f"\n  [{marker}] {cp_label}")
        print(f"  Status: {cp_status}  |  Confidence: {conf_str}")

        cp_cert = point.get("certificate_value")
        cp_inv = point.get("invoice_value")
        if cp_cert:
            cert_lines = str(cp_cert).split("\n")
            print(f"    Certificate: {cert_lines[0]}")
            for line in cert_lines[1:]:
                print(f"                 {line}")
        if cp_inv:
            inv_lines = str(cp_inv).split("\n")
            print(f"    Invoice:     {inv_lines[0]}")
            for line in inv_lines[1:]:
                print(f"                 {line}")

        rules = point.get("rules_applied", [])
        if rules:
            print(f"    Rules evaluated:")
            for rule in rules:
                rid = rule.get("rule_id", "?")
                outcome = rule.get("outcome", "?")
                icon = "+" if "match" in outcome.lower() or "accept" in outcome.lower() or "pass" in outcome.lower() or "verified" in outcome.lower() else "-" if "mismatch" in outcome.lower() or "fail" in outcome.lower() or "reject" in outcome.lower() else "~"
                print(f"      {icon} [{rid}] {outcome}")

        motivation = point.get("motivation")
        if motivation:
            print(f"    Motivation:")
            words = motivation.split()
            line = "      "
            for word in words:
                if len(line) + len(word) + 1 > 74:
                    print(line)
                    line = "      " + word
                else:
                    line += (" " if line.strip() else "") + word
            if line.strip():
                print(line)

    if overall.get("critical_failures"):
        print(f"\n  {'─' * 56}")
        print(f"  CRITICAL FAILURES:")
        for f in overall["critical_failures"]:
            print(f"    ✗ {f}")
    if overall.get("manual_review_triggers"):
        print(f"\n  {'─' * 56}")
        print(f"  MANUAL REVIEW TRIGGERS:")
        for t in overall["manual_review_triggers"]:
            print(f"    ? {t}")

    if is_manual_review:
        print(f"\n  {'─' * 56}")
        print(f"  MANUAL REVIEW REQUIRED — reason:")
        if overall.get("decision_summary"):
            words = overall["decision_summary"].split()
            line = "    "
            for word in words:
                if len(line) + len(word) + 1 > 74:
                    print(line)
                    line = "    " + word
                else:
                    line += (" " if line.strip() else "") + word
            if line.strip():
                print(line)
        for cp_name_key, cp_label_val in cp_labels.items():
            pt = cp.get(cp_name_key, {})
            pt_status = pt.get("status", "")
            if pt_status in ("MANUAL_REVIEW", "NOT_FOUND", "MISMATCH"):
                pt_motivation = pt.get("motivation", "")
                print(f"    [{pt_status}] {cp_label_val}")
                if pt_motivation:
                    print(f"      {pt_motivation[:200]}")

    print(f"\n  {'─' * 56}")
    print(f"  Tokens — Input: {input_tokens:,}, Output: {output_tokens:,}")

    # Save per-pair report
    safe_name = re.sub(r"[^\w\-]", "_", name)
    report_path = TESTREPORTS_DIR / f"{safe_name}_{pair['category']}.json"
    report_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

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


def print_summary(results: list[dict]):
    total = len(results)
    passed = sum(1 for r in results if r.get("status") in ("PASS", "REVIEW"))
    failed = sum(1 for r in results if r.get("status") == "FAIL") + sum(1 for r in results if "error" in r)
    review_count = sum(1 for r in results if r.get("status") == "REVIEW")

    print(f"\n{'=' * 60}")
    print(f"  SUMMARY: {total} pairs tested — {passed} passed, {failed} failed")
    print(f"  {'─' * 56}")
    if review_count:
        print(f"  ({review_count} marked MANUAL_REVIEW — not wrong, but needs human check)")
    print(f"  {'─' * 56}")
    for r in results:
        if "error" in r:
            print(f"    ERROR  {r['name']}: {r['error']}")
        else:
            icon = r["status"]
            line = f"    {icon:6s} {r['name']:30s}  expected={r['expected']:16s}  got={r['actual']}"
            if r["status"] == "REVIEW":
                line += f"  workflow={r['workflow']}"
            print(line)
            if r["status"] == "REVIEW" and r.get("manual_review_triggers"):
                for trigger in r["manual_review_triggers"]:
                    print(f"           ? {trigger}")
    print(f"  {'─' * 56}")
    total_in = sum(r.get("input_tokens", 0) for r in results)
    total_out = sum(r.get("output_tokens", 0) for r in results)
    print(f"  Total tokens — Input: {total_in:,}, Output: {total_out:,}")
    print(f"{'=' * 60}")


def run_chunk(chunk: list[dict], chunk_num: int, total_chunks: int) -> list[dict]:
    """Upload, submit, wait, and collect results for one chunk of pairs."""
    print(f"\n{'=' * 60}")
    print(f"  CHUNK {chunk_num}/{total_chunks}  ({len(chunk)} pairs)")

    batch_id = submit_batch(chunk)
    file_ids = json.loads(BATCH_STATE_FILE.read_text(encoding="utf-8")).get("file_ids", {})
    pair_by_id = {p["name"]: p for p in chunk}

    print(f"Polling batch status (checks every 30 s)...")
    batch = poll_batch(batch_id)

    if batch.status != "completed":
        print(f"Batch ended with status: {batch.status}")
        if getattr(batch, "error_file_id", None):
            errors = client.files.content(batch.error_file_id).text
            print("--- Batch errors ---")
            for line in errors.strip().splitlines()[:10]:
                print(line)
        elif getattr(batch, "errors", None):
            print(f"Errors: {batch.errors}")
        delete_uploaded_files(file_ids)
        BATCH_STATE_FILE.unlink(missing_ok=True)
        return []

    output_content = client.files.content(batch.output_file_id).text
    results = []
    for line in output_content.strip().splitlines():
        entry = json.loads(line)
        custom_id = entry["custom_id"]
        pair = pair_by_id.get(custom_id)
        if pair is None:
            print(f"WARNING: unknown custom_id in results: {custom_id}")
            continue
        response_body = entry.get("response", {}).get("body", {})
        error = entry.get("error")
        if error or not response_body:
            print(f"ERROR for {custom_id}: {error}")
            results.append({"name": custom_id, "error": str(error)})
            continue
        message = response_body["choices"][0]["message"]
        result = json.loads(message["content"])
        usage = response_body.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        results.append(print_pair_result(pair, result, input_tokens, output_tokens))

    delete_uploaded_files(file_ids)
    BATCH_STATE_FILE.unlink(missing_ok=True)
    return results


def main():
    all_pairs = get_document_pairs()
    if MAX_PAIRS is not None:
        all_pairs = all_pairs[:MAX_PAIRS]
    if not all_pairs:
        print(f"No document pairs found in {TESTSYSTEM_DIR}")
        return

    chunks = [all_pairs[i:i + BATCH_CHUNK_SIZE] for i in range(0, len(all_pairs), BATCH_CHUNK_SIZE)]
    print(f"Running {len(all_pairs)} pairs in {len(chunks)} chunks of up to {BATCH_CHUNK_SIZE}...")

    all_results = []
    for i, chunk in enumerate(chunks, 1):
        chunk_results = run_chunk(chunk, i, len(chunks))
        all_results.extend(chunk_results)
        if chunk_results:
            passed = sum(1 for r in chunk_results if r.get("status") in ("PASS", "REVIEW") and "error" not in r)
            failed = sum(1 for r in chunk_results if r.get("status") == "FAIL" or "error" in r)
            print(f"\n  Chunk {i} done: {passed} passed, {failed} failed  ({len(all_results)}/{len(all_pairs)} total so far)")

    print_summary(all_results)


if __name__ == "__main__":
    main()
