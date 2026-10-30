PY ?= python3
PILOT = data/nasa_stgermain_cop26
CORPUS_DIR ?= artifacts/corpus_tranche1
CORPUS_SOURCES ?= data/corpus_sources_v10.json
NATIVE_PY ?= .venv-native/bin/python
NATIVE_OUT ?= artifacts/native_motion_v1
SPEECH_OUT ?= artifacts/native_speech_probe

.PHONY: talk-setup talk-check help test pilot eval-mock eval-jev bench clean verify doctor corpus-acquire corpus-audit corpus-jobs studio studio-local studio-research studio-research-agent studio-researched native-preview native-test native-speech
help:
	@echo "make talk-setup  install the speech and display environments for a live talk"
	@echo "make talk-check  check microphone tools, recognition, Jev and displays (opens nothing, records nothing)"
	@echo "make native-preview  export a visual-only native motion sample headlessly (optional .venv-native)"
	@echo "make native-test     run native backend/Qt checks offscreen"
	@echo "make native-speech   real-paced speech recognition to native video, headlessly; choose a fresh SPEECH_OUT"
	@echo "make studio     open the preparation-first local app (use the access URL printed in the terminal)"
	@echo "make studio-local  enable optional local continuous speech recognition (.venv-asr required)"
	@echo "make studio-researched  unattended web research before preparation and during rehearsal"
	@echo "make studio-research  add background public-source lookup using existing Jev credentials"
	@echo "make studio-research-agent  connect an active web-capable research agent"
	@echo "make test       run the unit tests (stdlib only, no network, no key)"
	@echo "make pilot      score the windowed editor trace against the oracle trace (NASA pilot)"
	@echo "make eval-mock  run the strictly causal System-1 harness with the mock backend (plumbing check)"
	@echo "make eval-jev   same, against the real Jev API (needs JEV_API_KEY); writes artifacts/jev_eval.json"
	@echo "make bench      measure Jev latency from this machine (needs JEV_API_KEY)"
	@echo "make verify     offline tests, pilot, mock evaluation and preflight"
	@echo "make doctor     report available tools and missing frozen runtime files"
	@echo "make corpus-acquire  download 30 NASA caption candidates (network; rights review pending)"
	@echo "make corpus-audit    audit acquired candidates without claiming training readiness"
	@echo "make corpus-jobs     create independent oracle-editor prompts (does not run models)"

talk-setup:
	test -x .venv-native/bin/python || $(PY) -m venv .venv-native
	.venv-native/bin/python -m pip install -q -r requirements-native.txt
	test -x .venv-asr/bin/python || $(PY) -m venv .venv-asr
	.venv-asr/bin/python -m pip install -q torch --index-url https://download.pytorch.org/whl/cpu
	.venv-asr/bin/python -m pip install -q -r requirements-recorded-audio.txt
	.venv-asr/bin/python -c "import whisper; whisper.load_model('tiny.en', device='cpu')"

talk-check:
	$(NATIVE_PY) -m presenter.talk --check

test:
	$(PY) -m unittest discover -p "test_*.py"

native-preview:
	$(NATIVE_PY) -m presenter.native --demo --export-motion $(NATIVE_OUT)

native-test:
	$(NATIVE_PY) -m unittest test_native_output test_native_speech_probe

native-speech:
	$(NATIVE_PY) -m presenter.native_speech_probe --out-dir $(SPEECH_OUT)

studio:
	$(PY) -m presenter.server

studio-local:
	$(PY) -m presenter.server --asr-python .venv-asr/bin/python

studio-research:
	$(PY) -m presenter.server --research --asr-python .venv-asr/bin/python

studio-researched:
	$(PY) -m presenter.server --research-web --asr-python .venv-asr/bin/python

studio-research-agent:
	$(PY) -m presenter.server --research-bridge --asr-python .venv-asr/bin/python

pilot:
	$(PY) compare_traces_v10.py $(PILOT)/trace_llm_oracle.json $(PILOT)/trace_llm_causal.json --talk-s 815.42

eval-mock:
	$(PY) eval_system1_v10.py --backend mock --out artifacts/mock_eval.json

eval-jev:
	$(PY) eval_system1_v10.py --backend jev --out artifacts/jev_eval.json

bench:
	$(PY) bench_system1_v10.py --n 20 --out artifacts/jev_bench.json

doctor:
	$(PY) preflight_v10.py --out artifacts/readiness.json

verify: test pilot eval-mock doctor

corpus-acquire:
	$(PY) corpus_v10.py acquire-nasa --limit 30 --out-dir $(CORPUS_DIR) --sources $(CORPUS_SOURCES)

corpus-audit:
	$(PY) corpus_v10.py audit --corpus-dir $(CORPUS_DIR) --out artifacts/corpus_audit.json

corpus-jobs:
	$(PY) corpus_v10.py prepare-jobs --corpus-dir $(CORPUS_DIR)

clean:
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
