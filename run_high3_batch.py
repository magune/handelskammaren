"""Probe: kör FAIL/instabila par × 3 på gpt-5.4 + HIGH reasoning i BATCH.
Tre separata batchar -> HighEffort_run1/2/3. Skriver konsistens-sammanfattning
(är high mer stabil + lyfter den de instabila?). Jämför mot medium = FullrunResults.
OBS: GÖR RIKTIGA BATCH-ANROP (upp till 24 h). Kör endast efter godkännande.
"""
import time, json, glob
import fullrun as h

h.MODEL            = "gpt-5.4"
h.REASONING_EFFORT = "high"

AFFECTED = ["P0106","P0118","P0149","P0154","P0180","P023","P027","P032","P055",
            "P060","P084","P201","P214","P0191","SEG-24D-118957","P0172","P0151"]

def main():
    allp = {p["name"]: p for p in h.discover_pairs()}
    pairs = sorted((p for n,p in allp.items() if n.split("_")[0] in AFFECTED or n in AFFECTED),
                   key=lambda p: p["name"])
    pair_by_name = {p["name"]: p for p in pairs}
    print(f"{len(pairs)} par × 3 i BATCH (gpt-5.4/high), prompt {h.prompt_hash}")

    jobs = []  # [rep, dir, chunk_state]
    for rep in (1,2,3):
        d = h.BASE_DIR / f"HighEffort_run{rep}"; d.mkdir(exist_ok=True)
        h.RESULTS_DIR = d
        cs = h.submit_chunk(pairs, 0)
        jobs.append([rep, d, cs])

    pending = list(range(3))
    while pending:
        time.sleep(h.POLL_INTERVAL)
        for i in list(pending):
            rep, d, cs = jobs[i]
            b = h.api_call(h.client.batches.retrieve, cs["batch_id"])
            c = b.request_counts
            print(f"  [run{rep}] {b.status} {getattr(c,'completed','?')}/{getattr(c,'total','?')}", flush=True)
            if b.status in ("completed","failed","expired","cancelled"):
                h.RESULTS_DIR = d
                h.collect_chunk(b, cs, pair_by_name, {})
                h.delete_files(cs["file_ids"])
                pending.remove(i)

    def verds(d):
        o={}
        for f in glob.glob(f"{d}/*.json"):
            m=json.load(open(f)).get("_meta",{})
            if m.get("pair"): o[m["pair"]]=m.get("actual")
        return o
    med = verds("FullrunResults")
    r = [verds(f"HighEffort_run{k}") for k in (1,2,3)]
    print(f"\n{'PAR':24s} {'medium':14s} {'high1':14s} {'high2':14s} {'high3':14s} high-stabil?")
    for p in sorted(pair_by_name):
        hv=[r[k].get(p) for k in range(3)]
        stab = "STABIL" if len(set(hv))==1 else "FLIPPAR"
        print(f"{p:24s} {str(med.get(p))[:13]:14s} {str(hv[0])[:13]:14s} {str(hv[1])[:13]:14s} {str(hv[2])[:13]:14s} {stab}")

if __name__ == "__main__":
    main()
