# Live Presenter Toy — Status

## What works now

- speech-text driven semantic navigation;
- HOT/WARM semantic frontier;
- speculative prefetch using WARM neighbors;
- local corpus/RAG retrieval;
- topic-specific asset warming;
- telemetry and waste accounting;
- async AI adviser hook;
- off-graph ephemeral topic preparation;
- replayable rehearsal script;
- automatic final-state and event-log output.

## Empirical toy results

A controlled benchmark with artificial 250 ms asset retrieval delay showed:

- trajectory warming: ~0 ms wait when predicted node became HOT;
- reactive retrieval: ~251 ms wait after node became HOT.

A skip-branch rehearsal also showed the cost: predicted-but-skipped assets can be entirely wasted. That is desirable evidence for a later prefetch-budget policy, not a failure of the architecture.

## Real components vs simulated components

Real:

- semantic retrieval (TF-IDF over local corpus);
- semantic frontier;
- caching/prefetch;
- local RAG memory;
- async AI HTTP adapter;
- state/log protocol.

Simulated in the toy:

- speech stream (text lines stand in for streaming ASR);
- audience-facing renderer (JSON state stands in for Chromium/PWA);
- model responses unless a real endpoint is configured;
- external web retrieval.

## Recommended next gate

Attach the runtime to a real streaming STT client and a trivial browser renderer, then run a 10-minute hands-off rehearsal. Do **not** add more predictive complexity before that test.
