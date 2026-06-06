"""POC skärpta regler (artikelnr 4.3.2 + fakturadatum 4.3.5). Mål: P201,P055 (ska bli MISMATCH=PASS).
Guards: P004,P007,P008,P012,P016 (clean MATCH ska förbli PASS). SYNC."""
import fullrun as h
h.SYNC_MODE=True
h.ONLY_PAIRS=["P201","P055","P004","P007","P008","P012","P016"]
h.RESULTS_DIR=h.BASE_DIR/"Strengthen_poc"; h.RESULTS_DIR.mkdir(exist_ok=True)
h.main()
