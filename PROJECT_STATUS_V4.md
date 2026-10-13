# Live Presenter Toy v4 — Status

V4 completes the first credible end-to-end toy of the central thesis:

> semantic trajectory can prepare visual/retrieval work before the exact presentation need is stated.

## Working path

```text
streaming speech text
    ↓
semantic graph belief
    ↓
HOT / WARM frontier
    ↓
asset + corpus prefetch
    ↓
real Chromium audience stage
    ↓
final-speech commit
```

### Important execution contract

- interim speech may prepare (`WARM`) but may **not** move the projector;
- final speech may change semantic state and therefore the stage;
- explicit commands can force hold/resume/back/blank/sources/show-that/plot-that;
- stage mutations are coalesced so the browser does not chase every intermediate runtime state;
- AI advice is asynchronous and stale/revision-bound.

## Controlled prefetch experiment

With an artificial 240 ms asset-lookup cost:

- trajectory-prefetch promotion wait: ~0 ms;
- reactive promotion wait: ~243 ms.

In a branch that was warmed but skipped:

- trajectory speculation waste: 100% of the warmed asset fetches;
- reactive speculation waste: 0%.

This is the expected tradeoff and motivates a learned/budgeted WARM frontier rather than unlimited prefetch.

## Real Chromium

`rehearsal_compare_v4.py` drives the runtime through an actual Chromium page and captures screenshots for the semantic sequence:

`Generation Abundance → AI Slop → Examples → Mechanism → Evidence → Verification Burden → Provenance`

The audience surface contains no presenter buttons.

## External retrieval

A Wikimedia Commons image adapter is implemented behind the same background-search contract used by the offline demo adapter. The current execution sandbox could not resolve `commons.wikimedia.org`, so network retrieval was not falsely reported as validated. The offline/demo adapter remains the exercised rehearsal path.

## Remaining empirical gates

- real microphone/STT bridge on an actual presentation machine;
- real networked external-search run;
- longer (10–30 minute) hands-off presenter rehearsal;
- prefetch budget/priority policy derived from measured hit/waste/latency value;
- human evaluation against fixed deck and reactive-only versions.
