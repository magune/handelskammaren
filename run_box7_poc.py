"""POC ruta 7-fragmenterings-klausul. Mål: P0118,P027,P023,P032 (kategori i Quantity, separat rad/post).
Guards: P029,P0106 (kategori i Description -> ska FÖRBLI ej-PASS), P074 (MISMATCH-guard). SYNC."""
import fullrun as h
h.SYNC_MODE=True
h.ONLY_PAIRS=["P0118","P027","P023","P032","P029","P0106","P074"]
h.RESULTS_DIR=h.BASE_DIR/"Box7_poc"; h.RESULTS_DIR.mkdir(exist_ok=True)
h.main()
