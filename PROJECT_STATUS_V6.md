# Live Presenter Toy v6 — Status

## Current classification

**Bounded research/showcase tool with an object-continuous semantic stage. Not promoted to a priority project.**

V6's important change is not another input surface. It is that the runtime now has a model of the *audience-facing world*.

## Current stack

```text
presentation corpus / data
        ↓
semantic concept model
        ↓
live speech + discourse act
        ↓
representation broker
        ↓
grounded SceneSpec
        ↓
stable semantic stage objects
        ↓
object continuity + Chromium morph
        ↓
audience exposure memory
```

The AI adviser, audience model, asset retrieval and external search remain asynchronous/backstage components around this core.

## Capabilities now present

- semantic-only presentation model;
- HOT/WARM trajectory prefetch;
- interim/final speech contract;
- async AI adviser and off-graph topics;
- representation broker;
- intervention policy;
- deterministic Chromium rendering;
- local charts;
- source-bound evidence;
- audience-state input;
- stable stage-object identity;
- object-level transition planning;
- actual audience exposure memory;
- contextual provenance overlays;
- exposure-aware backstage audience adaptation;
- topic-movement firewall for representation requests;
- nonblocking Chromium View Transition morphs.

## Important failures found and addressed in v6

1. **Representation vocabulary could accidentally move the semantic topic.**
   - Corrected with promotion gating.

2. **Definition language could lose to incidental evidence vocabulary.**
   - Corrected by strengthening explicit-definition acts.

3. **Previous "audience memory" mostly meant transcript/semantic history.**
   - Corrected by recording objects only after actual render.

4. **Source view was generic recent retrieval context.**
   - Corrected by preferring refs attached to currently visible objects.

5. **Ephemeral topics inherited the prepared concept's stage identity.**
   - Corrected with semantic IDs on ephemeral scenes.

6. **The first implementation awaited the browser animation.**
   - Corrected so animation is visual-only and nonblocking.

## Verification

- Combined automated suite: **55 passing**.
- Complete suite run five consecutive times: **5 / 5 clean**.
- Chromium semantic rehearsal completes consistently.
- Current rehearsal transition counts: 1 enter / 12 morph / 2 crossfade.
- Observed unique stage semantic objects in the rehearsal: 32.
- Local browser mutation benchmark: median ~4.0 ms, p95 ~9.1 ms, max ~21.3 ms.

These browser numbers are local DOM mutation timings and should not be described as end-to-end presentation latency.

## What remains empirical

- real microphone/STT in room conditions;
- arbitrary paper→semantic graph quality with a real model;
- real web retrieval and licensing/ranking;
- presenter trust over a 10–30 minute talk;
- whether morphing improves rather than distracts;
- whether audience-state adaptation helps comprehension;
- whether trajectory-aware preparation materially beats very fast reactive behavior in real conditions.

## Current strongest thesis

> **A live presentation can be modeled as an evolving audience-visible semantic object system, rather than as a sequence of slides.**

V6 gives that thesis an executable form: concepts and evidence survive representation changes, and the runtime remembers what the audience has actually seen.
