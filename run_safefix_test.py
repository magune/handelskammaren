"""Verifiering av de 4 säkra promptfixarna + Combined. SYNC, separat mapp.

Fix-mål (ska bli PASS): P026 P048 (identifierare), P212 (metadata),
  P0179 (naken count), P0183 (stad≠land)
MISMATCH-guards (ska förbli PASS): P029 P074 P0101
Combined-guards (ska förbli PASS): P0186 P023 P032
Regressionsvakter (vanliga MATCH — fångar om skärpta reglerna överträffar): P004 P007 P008 P012 P016
Jämför mot FullrunResults/ (baslinje).
"""
import fullrun as h

h.SYNC_MODE  = True
h.ONLY_PAIRS = ["P026", "P048", "P212", "P0179", "P0183",
                "P029", "P074", "P0101",
                "P0186", "P023", "P032",
                "P004", "P007", "P008", "P012", "P016"]
h.RESULTS_DIR = h.BASE_DIR / "SafeFix_test"
h.RESULTS_DIR.mkdir(exist_ok=True)
h.main()
