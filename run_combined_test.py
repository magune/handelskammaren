"""Riktad omkörning efter joined-fields/Combined-ändringen. SYNC, separat mapp.

Pattern B-fix (ska bli PASS): P0106 P0123 P0186 P036 P065
Guards MISMATCH (ska förbli PASS): P029 P074 P0101
Guards MATCH/Pattern A (ska förbli PASS): P023 P032 P059  ; P0132 (Pattern A delvis)
Jämför mot FullrunResults/ (baslinje).
"""
import fullrun as h

h.SYNC_MODE  = True
h.ONLY_PAIRS = ["P0106", "P0123", "P0186", "P036", "P065",
                "P029", "P074", "P0101", "P023", "P032", "P059", "P0132"]
h.RESULTS_DIR = h.BASE_DIR / "JoinedCombined_test"
h.RESULTS_DIR.mkdir(exist_ok=True)
h.main()
