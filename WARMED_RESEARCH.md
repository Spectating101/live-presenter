# Reuse researched topics when they return

Live research now checks whether an earlier online source can support a returning
topic before repeating search and page retrieval. An early mention can pay the
retrieval cost while the speaker continues. A later, differently worded question
can reuse the quotation after a fresh relevance check. This does not predict an
unmentioned topic or remove the cost of its first lookup.

In two executions of the clearer typed script, the early heat-pipe mention fetched a Wikipedia
source. After returning to prepared pump notes, a differently worded heat-pipe
question put that source back at the stage API in **0.66 and 0.58 seconds**.
The latest fresh model check scored presentation relation 0.97 and topic support
0.96. The explicitly unrelated baking question was rejected (0.25 / 0.19) and
the prepared scene remained on stage. These are scripted API observations under
two code versions, not audio latency or independent editorial validation.
Their first lookups took 7.94 and 2.50 seconds respectively, without an
application result cache. External search/CDN caches and network conditions are
uncontrolled. The faster return amortizes that earlier work; it does not erase it.

The same work also repaired an audio regression: under machine load, four Torch
threads caused long recognition stalls. Two serial profiles per setting on
three recorded cue windows gave median decode times of 6.81 seconds with four
threads and 1.22 seconds with one. Five of six single-thread samples finished
within two seconds; one of six four-thread samples did. These are small offline
profiles under changing load, not a general ASR benchmark. The live recognizer
now uses one thread; its two-second decode deadline, freshness limits, model
and token limit are unchanged.

## Current behavior

The cache stays in server memory, with eight entries scoped to the approved
package and a five-minute lifetime from the initial completed lookup. Cache
reuse does not extend that lifetime. A normalized topic phrase must appear in
the latest utterance, rather than only in older context. Common function words
and plural endings are normalized; arbitrary synonyms do not qualify. This
local match nominates a candidate and does not authorize display.

For a returning topic, one bounded Jev call checks both the current presentation
relation (at least 0.65) and the actual cached quotation's support for that topic
within the current question (at least 0.85). A source can explain one side of a
comparison without supporting the whole comparison. That limited scope is
recorded explicitly. A rejection produces no new source display. An
accepted quotation keeps its original URL, source hash and retrieval timestamp,
with a separate revalidation timestamp. Only the quotation is reused
automatically: an earlier image has not been rechecked for the new context.
The online source stays provisional and outside the approved package.

Hold, Stop, manual selection, generation/package changes, topic freshness,
ordinary dwell and the hard worker deadline still control display. Revalidation
uses one assessment from the sixty-assessment budget, without consuming another
of the twelve full lookups. Exact-utterance cache reuse retains its existing
behavior. Topic reuse applies to the built-in provider workers, not an external
browsing-agent bridge.

The topic selector now asks for a concrete researchable concept rather than a
vague sentence fragment or a rewording of prepared content. If an assessment
identified no usable query, a newly corrected word can trigger reassessment
after 1.5 seconds. It need not wait the normal six-second lookup cooldown. This
helps when ASR corrects a partial phrase into a meaningful term. The existing
two-repeated-word exception remains for other rejected/idle requests. Both are
bounded by the assessment cap; neither lets a topic nomination bypass support
checks.

## Audio results and preserved repairs

The earlier seven-second result measured first matching recognition completion
to stage API observation. The new full 120-second Sivers replay measured **3.37
seconds** on that same definition, showing the same article and quotation hash.
It processed all 120 windows with no drops or timeouts. The time needed to hear
the cue, browser paint and physical presentation hardware are excluded.
An unchanged-code repeat measured **3.27 seconds**, again processing all 120
windows with no drops or timeouts and the same first source/quotation. Two
successes on one known recording do not establish a general latency guarantee.
After the cache-revalidation scope change, another complete replay measured
**5.03 seconds**, also with all 120 windows and no drops/timeouts. That attempt
selected a different secondary first-follower article, rather than the original
Sivers passage; its timing is for the first supported source, not identical
content. The three
post-topic-repair observations therefore span **3.27–5.03 seconds** (median
3.37). This variability matters: fresh lookup still takes seconds even when
recognition keeps up. Exact code versions are recorded per attempt.

The first single-thread audio attempt also processed all windows, but did not
show its first source until 45.15 seconds, about 18.37 seconds after matching
recognition. It had selected an unhelpful generic phrase before discovering the
specific first-follower topic. That slower attempt is preserved. The topic
selection and corrected-word reassessment changes precede the faster replay;
this evolving-code repair sequence is not an independent trial series.

The first typed probe also failed to demonstrate useful reuse: it fetched a
water-loop source, then rejected reuse for the heat-pipe question. It still
showed a heat-pipe page after an ambiguous baking comparison. The later fixture
uses a clearer early mention and an explicit request to set the heat-pipe topic
aside for baking. These are different scripts; later control rejection must not
be presented as a repeat of the identical earlier control. All attempts and
their actual utterances are retained.

The original typed script was then replayed twice under later code. It fetched
the heat-pipe source correctly, but still withheld the returning comparison:
support was 0.44, then 0.80 after clarifying that a quotation can explain one
side. The threshold remained 0.85. Both unrelated controls were also withheld.
This is an unresolved usefulness/coverage limitation; the fast result on the
clearer script does not establish that all legitimate rephrasings work.

The versioned record is
[`data/warmed_research_pilot_v1.json`](data/warmed_research_pilot_v1.json). It
includes the unchanged-code follow-up, earlier failures, code fingerprints,
source/package hashes, request counts and artifact hashes. Local comparisons
and API reconstructions are at `artifacts/warmed_research/index.html`.

## Reproduce

```bash
# Existing Jev credentials required. This probe uses typed HTTP, not audio.
python3 -m presenter.warm_research_demo --out-dir artifacts/a-new-warm-research

# Run separately from encoding and heavy tests. Requires the pinned Sivers WAV.
python3 -m presenter.researched_demo \
  --out-dir artifacts/a-new-single-thread-sivers \
  --fixture-json data/researched_rehearsal_sivers_v1.json
python3 -m presenter.rehearsal_report artifacts/a-new-single-thread-sivers --video
```

Use new directories so unsuccessful attempts are retained. Source-outline
approval in these probes is a developer fixture. No source results are injected
by the operator and no future transcript is supplied to preparation. Movies
reconstruct stage API events against the recorded audio; they are not browser
screen recordings.

Fresh, unanticipated online support still takes seconds and can fail. The
sub-second observation requires an already retrieved topic and a successful
current-context check. Unseen questions, independent judgments of source and
visual usefulness, microphone/browser/projector timing, and a functioning
generative preparation provider remain outstanding.
