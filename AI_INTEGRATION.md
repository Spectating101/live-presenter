# AI integration — deliberately off the critical path

The model is a **backstage adviser**, not the stage controller.

It receives only compact semantic state:

- presentation goal and weak planned route;
- current HOT node and visited nodes;
- recent transcript + newest fragment;
- known semantic nodes and scene kinds.

It may return:

- a likely current known concept;
- extra WARM nodes;
- background retrieval queries;
- a scene hint;
- one *ephemeral* topic when the presenter leaves the prepared graph.

It cannot directly render or automatically promote an invented topic. Known-node
AI promotions require a current, revision-bound result with confidence >= 0.86.
Older AI answers are discarded if new speech has arrived.

## Why this split

A presentation cannot freeze because a model takes two seconds. The deterministic
path therefore handles obvious speech immediately. AI improves ambiguous semantic
continuity and prepares material while the presenter keeps talking.

## Local model option

The adapter uses the OpenAI-compatible `/v1/chat/completions` wire format. This is
supported by local servers such as LM Studio and Ollama. Set:

```bash
export LIVEPRESENTER_AI_BASE_URL=http://127.0.0.1:1234/v1
export LIVEPRESENTER_AI_MODEL='<loaded model id>'
python runtime_v1.py --demo
```

For Ollama, the common compatible base is `http://127.0.0.1:11434/v1`.
No model/provider is required: without these variables, the toy runs its fast path.

## Web/image warming

`--wikimedia` activates a keyless Wikimedia Commons image-search adapter. Retrieval
is background-only; failures never block stage state. A real browser/search adapter
can later implement the same `SearchAdapter` contract.
