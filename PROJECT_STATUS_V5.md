# Live Presenter Toy v5 — Project Status

## Current classification

**Bounded research/showcase tool with a strong architecture; not yet promoted to a priority project.**

V5 establishes a credible semantic presentation runtime whose internal model is no longer shaped like a deck.

## Core capability

The runtime now accepts a semantic model consisting only of substantive concepts/claims, for example:

`Generation Abundance → AI Slop → Attention Selection → Verification Burden → Provenance`

During the presentation it infers how the current idea should be represented:

- hero/focus;
- definition;
- examples/image grid;
- causal flow;
- relationship map;
- evidence cards;
- local-data chart;
- bounded comparison.

The representation can change while the semantic topic remains fixed.

## Safety/grounding state

The renderer receives deterministic SceneSpecs. Representation decisions carry grounding metadata and confidence. Automatic comparison is disabled unless a genuinely grounded comparison can be produced. Source overlays, evidence cards, and charts remain bound to local source/data identities.

## Audience state

Audience-state input is available but advisory. Confusion/familiarity signals can prepare deeper scenes backstage, but the audience model cannot autonomously repaint the stage.

## AI state

The async AI adviser is optional and off the critical path. The runtime provides it with presentation goal/route, current/visited concepts, recent transcript, current RAG hits, and semantic nodes. It may advise known concepts, warm neighbors, retrieval queries, representation hints, and ephemeral tangent preparation. Stale responses are discarded.

## Corpus compilation

Two compiler paths now exist:

1. heuristic TF-IDF/KMeans compiler for deterministic/offline operation;
2. optional AI semantic compiler that explicitly asks for substantive concepts/claims rather than slide roles.

The heuristic compiler's known weakness is an important finding: lexical clustering cannot reliably tell real presentation content from instructions/tangents in mixed notes. Real model-based semantic compilation should therefore be treated as a meaningful component rather than cosmetic enhancement.

## Visual continuity

The browser renderer remains deterministic and fast. The next visual frontier is not more scene templates but **continuous visual composition**: stable semantic objects, object-level transitions, persistent spatial memory, and morphing between representations of the same concept.

## Verification state

Current combined automated suite: **44 passing**.

The v5 Chromium semantic-only rehearsal is repeatable and covers representation switching, grounded evidence/chart rendering, withheld comparison, audience-prepared explanation, and semantic topic movement.

## Priority decision

Keep the project bounded until one of these gates changes the decision:

- a real 10-minute hands-off presentation feels genuinely better than a conventional deck;
- trajectory prefetch produces material latency/flow benefits under real STT/network timing;
- presenter cognitive load is not increased by monitoring/recovering the AI;
- dynamic representations improve audience comprehension/relevance;
- the corpus→semantic model generalizes to real research material without heavy manual authoring.

Until then, the project's strongest value is **showcase + research prototype + personal presentation tool**.
