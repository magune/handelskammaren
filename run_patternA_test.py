"""Engångstest: kör Mönster A-fix-kandidaterna i SYNC-läge till en SEPARAT mapp.

Rör INTE FullrunResults/ (full 5.4-baslinje), V2_baseline_gpt55/ eller
FullrunResults_baseline/. Jämför mot FullrunResults/ (BASELINE_DIR) så vi ser
FAIL->PASS-övergångar efter promptändringen (Mönster A, rad 1274).
"""
import fullrun as h

h.SYNC_MODE  = True
h.ONLY_PAIRS = ["P0118", "P0132", "P023", "P032", "P059", "P0179"]
h.RESULTS_DIR = h.BASE_DIR / "PatternA_test_54med"
h.RESULTS_DIR.mkdir(exist_ok=True)
# BASELINE_DIR lämnas = FullrunResults för regressions-/övergångsjämförelse.

h.main()
