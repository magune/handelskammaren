import base64
import json
import re
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

BASE_DIR = Path(__file__).parent
TESTDATA_DIR = BASE_DIR / "Testdata"
TESTREPORTS_DIR = BASE_DIR / "Testreports"
PROMPT_FILE = BASE_DIR / "api_prompt.md"
SCHEMA_FILE = BASE_DIR / "schema_slim_strict.json"

TESTREPORTS_DIR.mkdir(exist_ok=True)

client = OpenAI()

system_prompt = PROMPT_FILE.read_text(encoding="utf-8")
schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))


def get_document_pairs():
    """Discover all document pairs from Testdata/Identiska and Testdata/Olika."""
    pairs = []

    for category, expected in [("Identiska", "IDENTICAL"), ("Olika", "NOT_IDENTICAL")]:
        category_dir = TESTDATA_DIR / category
        if not category_dir.exists():
            continue
        for pair_dir in sorted(category_dir.iterdir()):
            if not pair_dir.is_dir():
                continue
            pdfs = sorted(pair_dir.glob("*.pdf"))
            if len(pdfs) != 2:
                print(f"WARNING: {pair_dir.name} has {len(pdfs)} PDFs, skipping")
                continue
            pairs.append({
                "name": pair_dir.name,
                "category": category,
                "expected": expected,
                "files": pdfs,
            })

    return pairs


def encode_pdf_base64(path: Path) -> str:
    return base64.standard_b64encode(path.read_bytes()).decode("utf-8")


def call_llm(pdf_paths: list[Path]) -> dict:
    """Send two PDFs to GPT 5.4 and return parsed response + usage."""
    content = []
    for pdf_path in pdf_paths:
        b64 = encode_pdf_base64(pdf_path)
        content.append({
            "type": "file",
            "file": {
                "filename": pdf_path.name,
                "file_data": f"data:application/pdf;base64,{b64}",
            },
        })

    response = client.chat.completions.create(
        model="gpt-5.4",
        temperature=0,
        seed=42,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "verification_output",
                "strict": True,
                "schema": schema,
            },
        },
    )

    message = response.choices[0].message
    parsed = json.loads(message.content)
    usage = response.usage

    return {
        "result": parsed,
        "input_tokens": usage.prompt_tokens,
        "output_tokens": usage.completion_tokens,
    }


def main():
    pairs = get_document_pairs()
    if not pairs:
        print("No document pairs found in Testdata/")
        return

    results = []
    total = len(pairs)
    passed = 0
    failed = 0

    for pair in pairs:
        name = pair["name"]
        file_names = [f.name for f in pair["files"]]
        print(f"\n{'=' * 60}")
        print(f"  {name} ({pair['category']})")
        print(f"  File A: {file_names[0]}")
        print(f"  File B: {file_names[1]}")
        print(f"  Expected: {pair['expected']}")
        print(f"  Processing...", flush=True)

        try:
            llm_response = call_llm(pair["files"])
        except Exception as e:
            print(f"  ERROR: {e}")
            failed += 1
            results.append({"name": name, "error": str(e)})
            continue

        result = llm_response["result"]
        overall = result["overall_assessment"]
        comparison_result = overall["comparison_result"]
        input_tokens = llm_response["input_tokens"]
        output_tokens = llm_response["output_tokens"]

        is_pass = comparison_result == pair["expected"]
        is_manual_review = comparison_result == "MANUAL_REVIEW"
        if is_pass:
            passed += 1
            status = "PASS"
        elif is_manual_review:
            passed += 1
            status = "REVIEW"
        else:
            failed += 1
            status = "FAIL"

        # Print overall result
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

            # Extracted values
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

            # Rules applied trace
            rules = point.get("rules_applied", [])
            if rules:
                print(f"    Rules evaluated:")
                for rule in rules:
                    rid = rule.get("rule_id", "?")
                    outcome = rule.get("outcome", "?")
                    icon = "+" if "match" in outcome.lower() or "accept" in outcome.lower() or "pass" in outcome.lower() or "verified" in outcome.lower() else "-" if "mismatch" in outcome.lower() or "fail" in outcome.lower() or "reject" in outcome.lower() else "~"
                    print(f"      {icon} [{rid}] {outcome}")

            # Motivation
            motivation = point.get("motivation")
            if motivation:
                print(f"    Motivation:")
                # Word-wrap motivation at ~70 chars
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

        # Print failures / review triggers
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

        # Print why manual review is needed
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
            # List control points that triggered review
            for cp_name_key, cp_label_val in cp_labels.items():
                pt = cp.get(cp_name_key, {})
                pt_status = pt.get("status", "")
                if pt_status in ("MANUAL_REVIEW", "NOT_FOUND", "MISMATCH"):
                    pt_motivation = pt.get("motivation", "")
                    print(f"    [{pt_status}] {cp_label_val}")
                    if pt_motivation:
                        print(f"      {pt_motivation[:200]}")

        # Print tokens
        print(f"\n  {'─' * 56}")
        print(f"  Tokens — Input: {input_tokens:,}, Output: {output_tokens:,}")

        # Save report
        safe_name = re.sub(r"[^\w\-]", "_", name)
        report_path = TESTREPORTS_DIR / f"{safe_name}_{pair['category']}.json"
        report_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

        results.append({
            "name": name,
            "category": pair["category"],
            "expected": pair["expected"],
            "actual": comparison_result,
            "status": status,
            "workflow": overall.get("workflow_recommendation", "N/A"),
            "manual_review_triggers": overall.get("manual_review_triggers", []),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        })

    print(f"\n{'=' * 60}")
    print(f"  SUMMARY: {total} pairs tested — {passed} passed, {failed} failed")
    print(f"  {'─' * 56}")
    review_count = sum(1 for r in results if r.get("status") == "REVIEW")
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


if __name__ == "__main__":
    main()
