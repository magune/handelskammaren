"""
rerun_glitched.py — Detect and rerun document pairs with garbled/glitched model output.

Scans a results directory for:
  1. Parse errors (PARSE_ERROR or JSONDecodeError)
  2. Negative confidence values
  3. Gibberish in motivation text (low ratio of real words)

Resubmits detected pairs via Batch API and replaces the bad results.
"""

import datetime
import hashlib
import json
import re
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI, APIConnectionError, APITimeoutError

load_dotenv()

BASE_DIR        = Path(__file__).parent
TESTSYSTEM_DIR  = BASE_DIR / "Testdata" / "Testsystem företag"
PROMPT_FILE     = BASE_DIR / "api_prompt_54.md"
SCHEMA_FILE     = BASE_DIR / "schema_slim_strict.json"

# Which results directory to scan and fix
RESULTS_DIR     = BASE_DIR / "Fullrun54Results"
STATE_FILE      = BASE_DIR / "rerun_glitched_state.json"

MODEL            = "gpt-5.4"
REASONING_EFFORT = "medium"
INPUT_PRICE      = 1.875
OUTPUT_PRICE     = 7.50
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


def is_gibberish(text: str) -> bool:
    """Detect if text is garbled/nonsensical model output."""
    if not text or len(text) < 20:
        return False

    # Check for non-Latin script mixing (Chinese, Arabic, Japanese mixed with Latin)
    non_latin = len(re.findall(r'[^\x00-\x7F\xC0-\xFF]', text))
    if non_latin > len(text) * 0.15:
        return True

    # Check for excessive special characters
    special = len(re.findall(r'[→∬¬©∬ɒ→µ]', text))
    if special > 3:
        return True

    # Check word-like token ratio
    words = re.findall(r'[a-zA-ZäöåÄÖÅ]{3,}', text)
    if len(text) > 50 and len(words) < len(text) / 30:
        return True

    # Check for confidence values that are clearly wrong
    return False


REPORT_FILE = RESULTS_DIR / "glitch_report.json"


def detect_glitched_results() -> list[dict]:
    """Scan results directory and return detailed info about glitched pairs."""
    glitched = []
    seen = set()

    for f in sorted(RESULTS_DIR.glob("*.json")):
        if f.name == "glitch_report.json":
            continue

        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pair_name = f.stem.rsplit("_", 1)[0]
            if pair_name not in seen:
                seen.add(pair_name)
                print(f"  GLITCH [json_decode_error]: {pair_name}")
                glitched.append({
                    "pair": pair_name,
                    "glitch_type": "json_decode_error",
                    "detail": f"File {f.name} could not be parsed as JSON",
                    "original_result": None,
                    "original_confidence": None,
                })
            continue

        meta = data.get("_meta", {})
        actual = meta.get("actual", "")

        # Check 1: Parse error
        if actual == "PARSE_ERROR":
            pair_name = meta.get("pair", f.stem.rsplit("_", 1)[0])
            if pair_name not in seen:
                seen.add(pair_name)
                print(f"  GLITCH [parse_error]: {pair_name}")
                glitched.append({
                    "pair": pair_name,
                    "glitch_type": "parse_error",
                    "detail": "Model returned unparseable output (PARSE_ERROR status)",
                    "original_result": actual,
                    "original_confidence": None,
                })
            continue

        # Check 2: Negative or absurd confidence
        overall = data.get("overall_assessment", {})
        conf = overall.get("confidence", 0)
        if isinstance(conf, (int, float)) and conf < 0:
            pair_name = meta.get("pair", f.stem.rsplit("_", 1)[0])
            if pair_name not in seen:
                seen.add(pair_name)
                print(f"  GLITCH [negative_conf={conf}]: {pair_name}")
                glitched.append({
                    "pair": pair_name,
                    "glitch_type": "negative_confidence",
                    "detail": f"Overall confidence = {conf}",
                    "original_result": actual or overall.get("comparison_result"),
                    "original_confidence": conf,
                })
            continue

        # Check 3: Gibberish in control point motivations
        cp = data.get("control_points", {})
        glitch_detail = None
        for key in ["consignor", "consignee", "goods_description", "quantity", "country_of_origin"]:
            pt = cp.get(key, {})
            motiv = pt.get("motivation", "")
            cp_conf = pt.get("confidence", 0)

            if isinstance(cp_conf, (int, float)) and cp_conf < -10:
                glitch_detail = f"control_point '{key}' has confidence = {cp_conf}"
                break

            if isinstance(motiv, str) and is_gibberish(motiv):
                glitch_detail = f"control_point '{key}' has gibberish motivation: {motiv[:80]}..."
                break

        if glitch_detail:
            pair_name = meta.get("pair", f.stem.rsplit("_", 1)[0])
            if pair_name not in seen:
                seen.add(pair_name)
                print(f"  GLITCH [gibberish]: {pair_name} — {glitch_detail}")
                glitched.append({
                    "pair": pair_name,
                    "glitch_type": "gibberish",
                    "detail": glitch_detail,
                    "original_result": actual or overall.get("comparison_result"),
                    "original_confidence": conf,
                })

    return glitched


def discover_pairs(names: list[str]) -> list[dict]:
    """Find PDF files for specific pair names."""
    pair_files: dict[str, dict] = {}
    target = set(names)

    for pdf in sorted(TESTSYSTEM_DIR.glob("*.pdf")):
        parts = pdf.stem.split("_")
        if len(parts) < 3 or parts[1] not in ("MATCH", "MISMATCH") or parts[2] not in ("certificate", "invoice"):
            continue
        key = f"{parts[0]}_{parts[1]}"
        if key not in target:
            continue
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


def main():
    print(f"Scanning {RESULTS_DIR.name}/ for glitched results...\n")
    glitch_entries = detect_glitched_results()

    if not glitch_entries:
        print("\nNo glitched results found. All clean!")
        return

    glitched_names = [g["pair"] for g in glitch_entries]
    glitch_by_name = {g["pair"]: g for g in glitch_entries}

    print(f"\nFound {len(glitch_entries)} glitched pair(s):")
    for g in glitch_entries:
        print(f"  • {g['pair']:25s}  type={g['glitch_type']:20s}  {g['detail']}")

    pairs = discover_pairs(glitched_names)
    if not pairs:
        print("Could not find PDF files for glitched pairs.")
        return

    pair_by_name = {p["name"]: p for p in pairs}
    print(f"\nResubmitting {len(pairs)} pairs via Batch API...")

    # Upload and submit
    all_paths = list({f for p in pairs for f in p["files"]})
    print(f"  Uploading {len(all_paths)} PDFs...", flush=True)
    file_ids = upload_pdfs(all_paths)

    lines = [json.dumps(build_request(p, file_ids), ensure_ascii=False) for p in pairs]
    jsonl_bytes = "\n".join(lines).encode("utf-8")

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

    # Save state
    state = {
        "batch_id": batch.id,
        "pair_names": [p["name"] for p in pairs],
        "file_ids": file_ids,
        "prompt_hash": prompt_hash,
    }
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")

    # Poll
    print(f"\nPolling...\n", flush=True)
    while True:
        time.sleep(POLL_INTERVAL)
        batch_obj = api_call(client.batches.retrieve, batch.id)
        counts = batch_obj.request_counts
        print(f"  {batch_obj.status}  {counts.completed}/{counts.total}", flush=True)

        if batch_obj.status in ("completed", "failed", "expired", "cancelled"):
            break

    if not getattr(batch_obj, "output_file_id", None):
        print("Batch failed — no output.")
        delete_files(file_ids)
        return

    # Collect and overwrite results
    output_text = api_call(client.files.content, batch_obj.output_file_id).text
    fixed = 0
    still_glitched = 0

    for line in output_text.strip().splitlines():
        entry = json.loads(line)
        custom_id = entry["custom_id"]
        pair = pair_by_name.get(custom_id)
        if not pair:
            continue

        glitch_info = glitch_by_name.get(custom_id, {})

        error = entry.get("error")
        body = entry.get("response", {}).get("body", {})
        if error or not body:
            print(f"  ✗ {custom_id}: API error on retry")
            glitch_info["retry_outcome"] = "api_error"
            glitch_info["retry_result"] = None
            glitch_info["retry_confidence"] = None
            glitch_info["retry_status"] = None
            still_glitched += 1
            continue

        message = body["choices"][0]["message"]
        try:
            result = json.loads(message["content"])
        except json.JSONDecodeError:
            print(f"  ✗ {custom_id}: JSON error on retry")
            glitch_info["retry_outcome"] = "json_error"
            glitch_info["retry_result"] = None
            glitch_info["retry_confidence"] = None
            glitch_info["retry_status"] = None
            still_glitched += 1
            continue

        # Check if retry also glitched
        cp = result.get("control_points", {})
        retry_glitched = False
        for key in ["consignor", "consignee", "goods_description", "quantity", "country_of_origin"]:
            pt = cp.get(key, {})
            motiv = pt.get("motivation", "")
            cp_conf = pt.get("confidence", 0)
            if (isinstance(cp_conf, (int, float)) and cp_conf < -10) or (isinstance(motiv, str) and is_gibberish(motiv)):
                retry_glitched = True
                break

        if retry_glitched:
            print(f"  ✗ {custom_id}: still glitched after retry")
            glitch_info["retry_outcome"] = "still_glitched"
            glitch_info["retry_result"] = None
            glitch_info["retry_confidence"] = None
            glitch_info["retry_status"] = None
            still_glitched += 1
            continue

        overall = result.get("overall_assessment", {})
        comparison_result = overall.get("comparison_result", "?")
        conf = overall.get("confidence", "?")
        status = "PASS" if comparison_result == pair["expected"] else ("REVIEW" if comparison_result == "MANUAL_REVIEW" else "FAIL")

        result["_meta"] = {
            "tested_at":   datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "prompt_hash": prompt_hash,
            "model":       MODEL,
            "pair":        custom_id,
            "expected":    pair["expected"],
            "actual":      comparison_result,
            "status":      status,
            "rerun":       "glitch_retry",
        }

        # Overwrite the bad result
        out_path = RESULTS_DIR / f"{custom_id}_{pair['category']}.json"
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

        icon = "✓" if status == "PASS" else ("?" if status == "REVIEW" else "✗")
        print(f"  {icon} {custom_id:25s} → {comparison_result:16s} conf={conf}  [REPLACED]")

        glitch_info["retry_outcome"] = "fixed"
        glitch_info["retry_result"] = comparison_result
        glitch_info["retry_confidence"] = conf
        glitch_info["retry_status"] = status
        fixed += 1

    delete_files(file_ids)

    # Save glitch report
    report = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "results_dir": RESULTS_DIR.name,
        "model": MODEL,
        "prompt_hash": prompt_hash,
        "total_glitched": len(glitch_entries),
        "fixed": fixed,
        "still_glitched": still_glitched,
        "pairs": glitch_entries,
    }
    REPORT_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # Print summary
    print(f"\n{'='*70}")
    print(f"  GLITCH REPORT — {RESULTS_DIR.name}")
    print(f"  {'─'*66}")
    print(f"  Total glitched:    {len(glitch_entries)}")
    print(f"  Fixed on retry:    {fixed}")
    print(f"  Still glitched:    {still_glitched}")
    print(f"  {'─'*66}")
    for g in glitch_entries:
        outcome = g.get("retry_outcome", "pending")
        if outcome == "fixed":
            icon = "✓"
            detail = f"→ {g['retry_result']}  conf={g['retry_confidence']}  ({g['retry_status']})"
        else:
            icon = "✗"
            detail = f"→ {outcome}"
        print(f"  {icon} {g['pair']:25s}  glitch={g['glitch_type']:20s}  {detail}")
    print(f"  {'─'*66}")
    print(f"  Report saved: {REPORT_FILE.name}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
