"""check_rule_refs.py — referens-integritetskontroll för api_prompt.md mot Regelverk 11.

Read-only. Inga API-anrop. Körs före/efter varje prompt-ändring som regressionsvakt.

Rapporterar:
  1. Definierade regelnummer i prompten (rubriker + inline-deklarationer).
  2. Korsreferenser i prompten.
  3. HÄNGANDE referenser (refererad men aldrig definierad) — ska vara tom.
  4. DUBBELDEFINIERADE nummer (samma nummer deklarerat på flera ställen).
  5. Föräldralösa regler (definierad men aldrig refererad) — informativt.
  6. Prompt vs Regelverk 11: vilka regelverksnummer som saknar en prompt-deklaration
     på samma nummer (numrerings-gap).

Användning:
  python3 check_rule_refs.py          # rapport
  python3 check_rule_refs.py --json   # maskinläsbar (för before/after-diff)
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
import html
from pathlib import Path

BASE = Path(__file__).resolve().parent
PROMPT = BASE / "api_prompt.md"
DOCX = BASE / "Dokument" / "Regelverk 11- Operativt verifieringsregelverk för Certificate of Origin.docx"

NUM = r"\d+(?:\.\d+)*[a-z]?"          # 4, 4.4, 4.4.2.2, 4.4.2.2b
NUM_RE = re.compile(NUM)


def parse_prompt(text: str):
    """Return (defined: dict num->{lines,[],title}, referenced: dict num->count)."""
    defined: dict[str, dict] = {}
    referenced: dict[str, int] = {}
    lines = text.splitlines()

    def add_def(num, ln, title=""):
        d = defined.setdefault(num, {"lines": [], "title": ""})
        if ln not in d["lines"]:
            d["lines"].append(ln)
        if title and not d["title"]:
            d["title"] = title.strip()[:55]

    def clean(t):
        return re.sub(r"[*:#]", "", t).strip()

    for i, line in enumerate(lines, 1):
        s = line.strip()

        # (a) markdown-rubrik:  "#### 4.4.2.2 Titel"
        m = re.match(r"^#{1,6}\s+(" + NUM + r")\s+(.*)", s)
        if m:
            add_def(m.group(1), i, clean(m.group(2)))
        # (a2) toppsektion med punkt: "## 16. API input contract" -> definierar "16"
        m = re.match(r"^#{1,6}\s+(\d+)\.\s+(.*)", s)
        if m:
            add_def(m.group(1), i, clean(m.group(2)))
        # (b) fet rubrik som börjar med nummer: "**4.1.3.4.1 Titel**"
        m = re.match(r"^\*\*\s*(" + NUM + r")\s+(.*)", s)
        if m:
            add_def(m.group(1), i, clean(m.group(2)))
        # (c)/(e) inline-deklaration i fet rubrik/etikett som SLUTAR med ":**"
        #     t.ex. "**Fakturareferenser (4.4.5.2.1):**" eller "**... (avsnitt 4.3.3.1):**"
        if s.startswith("**") and s.rstrip().endswith(":**"):
            for mm in re.finditer(r"\((?:avsnitt\s+)?(" + NUM + r")\)", s):
                title = clean(re.sub(r"\((?:avsnitt\s+)?" + NUM + r"\)", "", s))
                add_def(mm.group(1), i, title)
        # (d) bar numrerad rubrikrad: "4.1.3.4.1 Titel"
        m = re.match(r"^(" + NUM + r")\s+([A-ZÅÄÖ].*)", s)
        if m and len(s) < 80:
            add_def(m.group(1), i, clean(m.group(2)))

    # --- References (hela texten) ---
    # avsnitt X / regel X / punkt X / enligt X / pröva X / se X / (X)
    for m in re.finditer(r"(?:avsnitt|regel|regel_id|punkt|enligt|pröva|se)\s+\"?(" + NUM + r")", text):
        referenced[m.group(1)] = referenced.get(m.group(1), 0) + 1
    for m in re.finditer(r"\((?:avsnitt\s+)?(" + NUM + r")\)", text):
        referenced[m.group(1)] = referenced.get(m.group(1), 0) + 1

    return defined, referenced


def parse_rulebook(docx: Path):
    """Return set of rule numbers defined in Regelverk 11 (headings)."""
    if not docx.exists():
        return None
    z = zipfile.ZipFile(docx)
    xml = z.read("word/document.xml").decode("utf-8", "ignore")
    paras = re.split(r"</w:p>", xml)
    nums = {}
    for p in paras:
        t = html.unescape("".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", p))).strip()
        # rubrik: "4.4.2.1 Särskilt krav – vikt"  (nummer + versal titel)
        m = re.match(r"^(\d+(?:\.\d+)*)\s+([A-ZÅÄÖ].*)", t)
        if m and len(t) < 90:
            nums[m.group(1)] = m.group(2)[:50]
    return nums


def sort_key(num):
    parts = re.split(r"\.", re.sub(r"([a-z])", r".\1", num))
    return [int(p) if p.isdigit() else p for p in parts]


def main():
    text = PROMPT.read_text(encoding="utf-8")
    defined, referenced = parse_prompt(text)
    rulebook = parse_rulebook(DOCX)

    defset = set(defined)
    refset = set(referenced)
    dangling = sorted(refset - defset, key=sort_key)
    dups = sorted({n for n, v in defined.items() if len(v["lines"]) > 1}, key=sort_key)
    orphans = sorted(defset - refset, key=sort_key)

    if "--json" in sys.argv:
        print(json.dumps({
            "defined": sorted(defset, key=sort_key),
            "referenced": sorted(refset, key=sort_key),
            "dangling": dangling,
            "duplicates": dups,
            "orphans": orphans,
        }, ensure_ascii=False, indent=2))
        return

    print(f"PROMPT: {len(defset)} definierade regelnummer, {len(refset)} unika refererade\n")

    print(f"[1] HÄNGANDE REFERENSER (refererad men ej definierad): {len(dangling)}")
    print("    (ska vara 0 — annars pekar prompten på ett regelnummer som inte finns)")
    for n in dangling:
        print(f"      {n}  (refererad {referenced[n]}x)")

    print(f"\n[2] DUBBELDEFINIERADE nummer: {len(dups)}")
    print("    (samma nummer som rubrik på flera ställen — kan vara avsiktligt, granska)")
    for n in dups:
        print(f"      {n}  rader {defined[n]['lines']}")

    print(f"\n[3] FÖRÄLDRALÖSA regler (definierad men aldrig refererad): {len(orphans)}  [informativt]")
    print("      " + ", ".join(orphans))

    if rulebook is not None:
        rb = set(rulebook)
        print(f"\n[4] REGELVERK 11: {len(rb)} regelnummer i dokumentet")
        gap = sorted(rb - defset, key=sort_key)
        print(f"    Regelverksnummer UTAN prompt-deklaration på samma nummer: {len(gap)}")
        for n in gap:
            print(f"      RV11 {n:10s} '{rulebook[n]}'  — saknas/annan numrering i prompten")
        common = sorted(rb & defset, key=sort_key)
        print(f"\n    Gemensamma nummer (finns i båda): {len(common)}")

        # [5] SEMANTISK DRIFT: samma nummer, olika regel (titel skiljer markant)
        def norm(t):
            return re.sub(r"[^a-zåäö0-9]", "", (t or "").lower())
        drift = []
        for n in common:
            pt = defined[n]["title"]
            rt = rulebook[n]
            np_, nr = norm(pt), norm(rt)
            # match om den ena titeln är delsträng av den andra (samma regel, ev. olika ordval)
            if np_ and nr and not (np_[:12] in nr or nr[:12] in np_):
                drift.append((n, pt, rt))
        print(f"\n[5] SEMANTISK DRIFT — samma NUMMER men olika REGEL: {len(drift)}")
        print("    (KRITISKT: här pekar samma rule_id på olika saker i prompt vs regelverk)")
        for n, pt, rt in drift:
            print(f"      {n:10s} PROMPT: '{pt}'")
            print(f"      {'':10s} RV11  : '{rt}'\n")
    else:
        print("\n[4] Regelverk 11-docx hittades inte — hoppar över gap-analys.")


if __name__ == "__main__":
    main()
