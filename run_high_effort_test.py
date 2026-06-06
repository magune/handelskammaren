"""Kostnadsbegränsad probe: kör de FAIL/instabila paren på gpt-5.4 + HIGH reasoning,
SYNC, separat mapp. Jämför verdikt mot medium-körningen (FullrunResults)."""
import fullrun as h
h.MODEL            = "gpt-5.4"
h.REASONING_EFFORT = "high"
h.SYNC_MODE        = True
h.ONLY_PAIRS = [
    # nuvarande 13 FAIL
    "P0106","P0118","P0149","P0154","P0180","P023","P027","P032","P055","P060","P084","P201","P214",
    # flippare/instabila (regressioner + kända)
    "P0191","SEG-24D-118957","P0172","P0151",
]
h.RESULTS_DIR = h.BASE_DIR / "HighEffort_test"
h.RESULTS_DIR.mkdir(exist_ok=True)
h.main()
