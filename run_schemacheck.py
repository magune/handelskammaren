"""1-par schema-koll: verifierar att manual_review_reason emitteras och att
strikt-schemat inte spräcker svaret. SYNC, separat mapp. Engångs."""
import fullrun as h
h.SYNC_MODE  = True
h.ONLY_PAIRS = ["P203"]
h.RESULTS_DIR = h.BASE_DIR / "SchemaCheck_test"
h.RESULTS_DIR.mkdir(exist_ok=True)
h.main()
