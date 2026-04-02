"""
fullrun_opus.py — Run all 242 pairs through Claude Opus 4.6 via Anthropic Batch API.

Uses api_prompt_54.md — tuned for decisive final verdicts.
Est. cost: ~$35 based on observed ~36k input / ~4.4k output tokens per pair
           (Batch API: $2.50/$12.50 per 1M tokens — 50% off standard).

Results saved to: FullrunOpusResults/
State file:       fullrun_opus_state.json  (resume-safe)
"""

import base64
import datetime
import hashlib
import json
import time
from pathlib import Path

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request
from dotenv import load_dotenv

load_dotenv()

BASE_DIR       = Path(__file__).parent
TESTSYSTEM_DIR = BASE_DIR / "Testdata" / "Testsystem företag"
RESULTS_DIR    = BASE_DIR / "FullrunOpusResults"
PROMPT_FILE    = BASE_DIR / "api_prompt_54.md"
SCHEMA_FILE    = BASE_DIR / "schema_slim_strict_anthropic.json"
STATE_FILE     = BASE_DIR / "fullrun_opus_state.json"

RESULTS_DIR.mkdir(exist_ok=True)

MODEL          = "claude-opus-4-6"
INPUT_PRICE    = 2.50   # $/1M tokens (Batch API = 50% off $5.00)
OUTPUT_PRICE   = 12.50  # $/1M tokens (Batch API = 50% off $25.00)
COST_LIMIT_USD = 50.0
CHUNK_SIZE     = 20     # pairs per batch (Anthropic allows up to 100k requests/batch)
POLL_INTERVAL  = 60     # seconds between status checks

client        = anthropic.Anthropic()
system_prompt = PROMPT_FILE.read_text(encoding="utf-8")
prompt_hash   = hashlib.sha256(system_prompt.encode()).hexdigest()[:12]
schema        = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
# PDF encoding (base64 inline — no Files API needed)
# ---------------------------------------------------------------------------

def encode_pdf(path_str: str) -> str:
    """Read a PDF and return base64-encoded content."""
    return base64.standard_b64encode(Path(path_str).read_bytes()).decode("utf-8")


# ---------------------------------------------------------------------------
# Build batch request
# ---------------------------------------------------------------------------

def build_request(pair: dict) -> Request:
    cert_path, inv_path = pair["files"][0], pair["files"][1]
    return Request(
        custom_id=pair["name"],
        params=MessageCreateParamsNonStreaming(
            model=MODEL,
            max_tokens=16000,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": encode_pdf(cert_path),
                        },
                        "title": "Certificate of Origin",
                    },
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": encode_pdf(inv_path),
                        },
                        "title": "Invoice",
                    },
                ],
            }],
        ),
    )


# ---------------------------------------------------------------------------
# Submit chunk
# ---------------------------------------------------------------------------

def submit_chunk(chunk: list[dict], chunk_idx: int) -> dict:
    print(f"  [chunk {chunk_idx+1}] Encoding {len(chunk)} pairs ({len(chunk)*2} PDFs)...", flush=True)

    requests = [build_request(p) for p in chunk]
    print(f"  [chunk {chunk_idx+1}] Submitting batch ({len(requests)} requests)...", flush=True)

    batch = client.messages.batches.create(
        requests=requests,
    )
    print(f"  [chunk {chunk_idx+1}] Batch submitted: {batch.id}  status={batch.processing_status}", flush=True)
    return {
        "chunk_idx":  chunk_idx,
        "batch_id":   batch.id,
        "pair_names": [p["name"] for p in chunk],
        "done":       False,
    }


# ---------------------------------------------------------------------------
# Result collection
# ---------------------------------------------------------------------------

def collect_chunk(batch_id: str, pair_by_name: dict) -> list[dict]:
    results = []
    for result in client.messages.batches.results(batch_id):
        custom_id = result.custom_id
        pair = pair_by_name.get(custom_id)
        if pair is None:
            continue

        if result.result.type == "errored":
            err = result.result.error
            print(f"    ✗ {custom_id}: API error — {err}", flush=True)
            results.append({"name": custom_id, "error": str(err)})
            continue

        if result.result.type != "succeeded":
            print(f"    ✗ {custom_id}: unexpected result type {result.result.type}", flush=True)
            results.append({"name": custom_id, "error": result.result.type})
            continue

        message = result.result.message
        tok_in  = message.usage.input_tokens
        tok_out = message.usage.output_tokens

        # Extract JSON from response content
        text_content = next((b.text for b in message.content if b.type == "text"), None)
        if text_content is None:
            print(f"    ✗ {custom_id}: no text content in response", flush=True)
            results.append({"name": custom_id, "error": "no text content"})
            continue

        # Strip markdown code fences if present (Opus wraps JSON in ```json ... ```)
        cleaned = text_content.strip()
        if cleaned.startswith("```"):
            first_nl = cleaned.index("\n")
            cleaned = cleaned[first_nl+1:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as e:
            print(f"    ✗ {custom_id}: JSONDecodeError: {e}", flush=True)
            results.append({"name": custom_id, "error": f"JSONDecodeError: {e}"})
            continue

        overall           = parsed["overall_assessment"]
        comparison_result = overall["comparison_result"]
        is_pass           = comparison_result == pair["expected"]
        is_review         = comparison_result == "MANUAL_REVIEW"
        status            = "PASS" if is_pass else ("REVIEW" if is_review else "FAIL")
        conf              = overall.get("confidence", "?")

        status_icon = "✓" if status == "PASS" else ("?" if status == "REVIEW" else "✗")
        print(f"    {status_icon} {custom_id:35s} {status:6s}  got={comparison_result:14s}  conf={conf}", flush=True)

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

        parsed["_meta"] = {
            "tested_at":   datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "prompt_hash": prompt_hash,
            "model":       MODEL,
            "pair":        custom_id,
            "expected":    pair["expected"],
            "actual":      comparison_result,
            "status":      status,
        }
        out_path = RESULTS_DIR / f"{custom_id}_{pair['category']}.json"
        out_path.write_text(json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8")

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

    est_cost = cost_usd(len(pairs) * 36000, len(pairs) * 4400)
    print(f"fullrun_opus — model={MODEL}  prompt={PROMPT_FILE.name}  hash={prompt_hash}")
    print(f"{len(pairs)} pairs in {len(chunks)} chunks of {CHUNK_SIZE}")
    print(f"Cost limit: ${COST_LIMIT_USD}  (est. ~${est_cost:.2f} based on 36k/4.4k tok/pair)")

    state = load_state()
    if state and state.get("prompt_hash") != prompt_hash:
        print("Prompt changed — starting fresh.")
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
                                "name":          name,
                                "category":      pair["category"],
                                "expected":      pair["expected"],
                                "actual":        meta.get("actual", ""),
                                "status":        meta.get("status", ""),
                                "input_tokens":  0,
                                "output_tokens": 0,
                            })
                        except Exception:
                            pass
        cumulative_cost = state.get("cumulative_cost", 0.0)
        print(f"Resuming — {len(completed_chunks)} chunks already done, cost so far ${cumulative_cost:.4f}")

    if state is None:
        state = {"prompt_hash": prompt_hash, "chunks": [], "cumulative_cost": 0.0}

    # Submit all pending chunks
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

    # Poll all pending batches
    while pending:
        time.sleep(POLL_INTERVAL)
        still_pending = []
        for chunk_state in pending:
            chunk_idx = chunk_state["chunk_idx"]
            batch = client.messages.batches.retrieve(
                chunk_state["batch_id"],
            )
            counts = batch.request_counts
            print(
                f"  [chunk {chunk_idx+1}] {batch.processing_status}"
                f"  succeeded={counts.succeeded}/{counts.processing + counts.succeeded + counts.errored}",
                flush=True,
            )

            if batch.processing_status == "ended":
                print(f"  [chunk {chunk_idx+1}] Collecting results...", flush=True)
                results = collect_chunk(batch.id, pair_by_name)

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
            print(f"  {len(still_pending)} chunks still running — {len(all_results)}/{len(pairs)} pairs done so far...\n", flush=True)
        else:
            pending = []

    print_progress(all_results, len(pairs), cumulative_cost)
    print_summary(all_results, cumulative_cost)


if __name__ == "__main__":
    main()
