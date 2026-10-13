PY ?= python3
PILOT = data/nasa_stgermain_cop26

.PHONY: help test pilot eval-mock eval-jev bench clean
help:
	@echo "make test       run the unit tests (stdlib only, no network, no key)"
	@echo "make pilot      score the windowed editor trace against the oracle trace (NASA pilot)"
	@echo "make eval-mock  run the strictly causal System-1 harness with the mock backend (plumbing check)"
	@echo "make eval-jev   same, against the real Jev API (needs JEV_API_KEY); writes artifacts/jev_eval.json"
	@echo "make bench      measure Jev latency from this machine (needs JEV_API_KEY)"

test:
	$(PY) -m unittest discover -p "test_*.py"

pilot:
	$(PY) compare_traces_v10.py $(PILOT)/trace_llm_oracle.json $(PILOT)/trace_llm_causal.json --talk-s 815.42

eval-mock:
	$(PY) eval_system1_v10.py --backend mock

eval-jev:
	@test -n "$$JEV_API_KEY" || (echo "set JEV_API_KEY first (see .env.example)"; exit 1)
	$(PY) eval_system1_v10.py --backend jev --out artifacts/jev_eval.json

bench:
	@test -n "$$JEV_API_KEY" || (echo "set JEV_API_KEY first (see .env.example)"; exit 1)
	$(PY) bench_system1_v10.py --n 20

clean:
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
