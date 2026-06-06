"""Rättvis motpart: samma 17 par × 3 på gpt-5.4 + MEDIUM i BATCH.
-> MedEffort_run1/2/3. För high-vs-medium-stabilitetsjämförelse."""
import time, json, glob
import fullrun as h
h.MODEL            = "gpt-5.4"
h.REASONING_EFFORT = "medium"
AFFECTED = ["P0106","P0118","P0149","P0154","P0180","P023","P027","P032","P055",
            "P060","P084","P201","P214","P0191","SEG-24D-118957","P0172","P0151"]
def main():
    allp={p["name"]:p for p in h.discover_pairs()}
    pairs=sorted((p for n,p in allp.items() if n.split("_")[0] in AFFECTED or n in AFFECTED), key=lambda p:p["name"])
    pbn={p["name"]:p for p in pairs}
    print(f"{len(pairs)} par × 3 i BATCH (gpt-5.4/medium), prompt {h.prompt_hash}")
    jobs=[]
    for rep in (1,2,3):
        d=h.BASE_DIR/f"MedEffort_run{rep}"; d.mkdir(exist_ok=True)
        h.RESULTS_DIR=d
        jobs.append([rep,d,h.submit_chunk(pairs,0)])
    pending=list(range(3))
    while pending:
        time.sleep(h.POLL_INTERVAL)
        for i in list(pending):
            rep,d,cs=jobs[i]
            b=h.api_call(h.client.batches.retrieve,cs["batch_id"]); c=b.request_counts
            print(f"  [med-run{rep}] {b.status} {getattr(c,'completed','?')}/{getattr(c,'total','?')}",flush=True)
            if b.status in ("completed","failed","expired","cancelled"):
                h.RESULTS_DIR=d; h.collect_chunk(b,cs,pbn,{}); h.delete_files(cs["file_ids"]); pending.remove(i)
    print("KLART — MedEffort_run1/2/3 skrivna.")
if __name__=="__main__":
    main()
