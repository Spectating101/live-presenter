# Faster first source during live research

The follow-up in [`WARMED_RESEARCH.md`](WARMED_RESEARCH.md) repairs the recognition
failure, measures speech recognition to stage API again, and adds fast checked
reuse across different phrasings. The original measurements below are retained.

The live web worker can now publish a source quotation after it passes the topic
and support checks, while optional image work continues. Three paired probes of
the same known Sivers question reduced median backend first-result time from
**5.36 to 3.67 seconds** (31.6%). This is a measured backend improvement; a new
full-audio replay failed at recognition and provides **no new speech-to-stage
latency result**.

| Measurement | Previous code | Progressive code |
| --- | --- | --- |
| Backend first supported result, three serial probes | 5.26–6.93 s; median 5.36 s | 3.49–4.06 s; median 3.67 s |
| Backend final result, same probes | 5.26–6.93 s | 3.86–4.65 s |
| Separate 120 s TED audio replay | Source reached stage API 7.08 s after first matching ASR completion estimate | No new source; recognition processed 5/120 windows, dropped 115, timed out 9 times |

The backend probes alternate execution order and use fresh child processes with
no application result-cache hit. All six returned the same Sivers article and
quotation hash. External search/CDN caches, network conditions and other machine
work remain uncontrolled. Three repetitions of one development question cannot
establish general reliability, a latency percentile or editorial usefulness.
The historical 7.08-second audio result includes controller scheduling and stage
API observation; it must not be compared directly with the new backend numbers.

## What changed

The worker searches after identifying a related topic, then races the first
three public result pages. It selects an actual fetched passage and asks the
separate source-support question before publishing. This removes a sequential
page-selection call and avoids waiting for a slow secondary page or optional
image lookup before the first checked source. A faster supported source may win
over a slower primary source; the six probes retained the same primary article,
but broader source-quality evaluation remains outstanding.

Optional Commons image discovery starts in parallel. A later image still needs
its own metadata-support check and bounded raster download. An image of the same
source can replace the initial quote during the stage dwell; a new subject
cannot use that exception. Hold, Stop, manual changes, package/generation
changes, topic freshness and cancellation still veto publication. An enrichment
failure preserves an already checked quotation. The approved package is not
modified. History records the first publication and final outcome under one
request ID.

The normal automatic assessment cooldown remains six seconds. After at least
1.5 seconds, an idle/rejected request can be reconsidered when two new words
outside the prepared material recur in successive recognized speech fragments.
This allows a developing cue to be noticed sooner without waiting the full
cooldown. The sixty-assessment/twelve-lookup caps remain. This scheduling change
has unit coverage but was not measured successfully in the failed audio replay.

Background relevance remains at least 0.40; automatic publication requires topic
relation at least 0.65 and source support at least 0.85. Image metadata needs at
least 0.85 independently of candidate ranking. These are model scores, not
independent fact checks or calibrated guarantees. Existing DNS/TLS, redirect,
response-size, raster and 25-second process limits remain in force. Image pixels
are not semantically verified. Preparation still waits for its complete source
set so the presenter can review it before approval.

## Why the audio run failed

The 120-second replay used the same pinned Sivers audio, ordinary one-second PCM
submission and unchanged tiny.en recognizer with a two-second decode deadline.
Only five windows completed; the first-follower cue never reached research.
There was no automatic research stage change. The failed attempt is preserved,
including its result, source/package hashes, worker counts and reconstructed
video. It is not replaced by the successful backend probes.

Three subsequent isolated four-second cue samples also exceeded the unchanged
two-second recognition budget. Recognizer startup took 17–25 seconds. The
six-core machine's one-minute load average was approximately 21–27 during that
diagnostic; a contemporaneous CPU-pressure sample recorded 68% some-stall time
over ten seconds. This is consistent with CPU contention, but does not isolate
it as the sole cause. Other applications were not stopped. Recognition's
deadline was not increased to manufacture a successful live result.

## Reproduce and inspect

The public measurements, code fingerprints and private-artifact hashes are in
[`data/faster_live_research_v1.json`](data/faster_live_research_v1.json). Local
results remain ignored; they contain retrieved source material rather than
redistributed quotations or images in the public manifest.

```bash
# Requires the earlier saved Sivers rehearsal and existing Jev credentials.
git worktree add --detach artifacts/research_latency_baseline 2f63c85
python3 -m presenter.research_latency \
  --folder artifacts/researched_rehearsal_sivers_v1 \
  --baseline-root artifacts/research_latency_baseline \
  --out-dir artifacts/a-new-latency-comparison
git worktree remove artifacts/research_latency_baseline

# Run audio separately from encoding/tests on an otherwise available machine.
python3 -m presenter.researched_demo \
  --out-dir artifacts/a-new-faster-sivers-rehearsal \
  --fixture-json data/researched_rehearsal_sivers_v1.json
python3 -m presenter.rehearsal_report artifacts/a-new-faster-sivers-rehearsal --video
```

Use a new output directory per attempt. The local comparison is
`artifacts/faster_live_research/index.html`; the failed audio replay is
`artifacts/faster_rehearsal_sivers_v1/index.html`. Its movie reconstructs stage
API observations against real recorded audio. It is not a browser recording,
physical microphone test or independent visual-quality judgment.

Fresh browsing still takes seconds here: the optimized worker spent roughly
1.4–1.8 seconds after search results waiting for its first page, before the
remaining source checks. Prepared selection and exact-context cache reuse avoid
that wait. Anticipatory retrieval during an explanation is a possible next step
toward having support ready at the cue; it has not been implemented or proven by
this experiment. The immediate next acceptance check is a successful frozen-code
audio replay with adequate CPU availability, followed by unseen questions and
independent judgments of whether the first source is useful.
