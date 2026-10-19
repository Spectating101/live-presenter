# Research before preparation and during continuous speech

This experiment extends `LIVE_RESEARCH.md` with an unattended public-web worker
and automatic preparation research. No operator has to answer a research job
while the rehearsal runs. It remains a development prototype, with an extractive
preparation fallback and experimental public search integration.

```bash
make studio-researched
# Typed rehearsal without the optional ASR environment:
python3 -m presenter.server --research-web
```

This uses the existing Jev credentials and local ASR setup. Before building the
first draft, the worker searches from the presentation title and uses the brief
to judge relevance. It opens public source pages, extracts a short actual-source
quotation, and looks for a licensed Commons image. Retrieved material becomes
part of the draft's source list, with provenance and attribution. The presenter
reviews those sources and visuals before approval. Edits to the title, brief,
audience or supplied materials trigger new preparation research; an unchanged
conversation does not repeat it. The preparation view also has a refresh button.

On this machine, choose **Source outline** as the preparation partner when
creating a presentation: the installed conversational provider is currently
quota-blocked. Automatic online procurement still runs in that mode. Its draft
remains extractive rather than a generative discussion of the explanation.

The default studio keeps its existing supplied-material workflow. Online
preparation is enabled explicitly by `--research-web`; the interface discloses
that the title, brief and topic context are sent to Jev/public source services.

During rehearsal, enabling Live research permits the worker to search for
related subjects absent from the prepared package. Prepared selection continues
locally. New sources remain visibly provisional, with source links. The approved
package is unchanged. Hold, Stop, manual selection, superseding speech, topic
freshness and process deadlines retain their authority over late results.

## Retrieval and display are separate decisions

The worker merges overlapping, past-only speech windows to form a developing
question. A selected query must use words actually present in that speech.
Prepared coverage is checked separately from the broader subject relationship.
An uncertain relationship may justify background retrieval. It does not by
itself justify a new public visual.

In web mode, source/page/image selection ranks finite candidates. The worker then
asks a separate yes/no support question about the selected actual-source quote
and, where available, image metadata. Ranking confidence is not treated as a
measure of factual support. These are separate questions to the same Jev model,
not independent editorial review or calibrated guarantees.

TypeSafe documents Choice confidence as a measure of how concentrated the
option distribution is. Several useful alternatives can lower that confidence;
it is not a direct verdict that the selected passage is unsupported. See the
[official Choice reference](https://docs.typesafe.ai/primitives/choice).

Current provisional settings allow background lookup at related probability
0.40; automatic display additionally requires at least 0.65, a separate source
support score of at least 0.85, current context and stage eligibility. Image
metadata must also reach 0.85. Low-relation results can stay backstage for review.
No image pixels are semantically verified by the app. These settings were
changed while repairing known development failures; they need independent
evaluation before making reliability claims.

The rehearsal budget distinguishes up to sixty topic assessments from twelve
new lookup attempts. A rejected ambiguous fragment that never produces a search
query does not consume a lookup slot. The six-second automatic request cooldown,
latest-only scheduling, eight-entry/five-minute exact-query cache, 20-second
topic freshness window and 25-second provider-process budget remain in effect.

## Public web integration

The worker reads ordinary Brave public HTML search results, opens selected public
HTTPS pages, and obtains attributed PNG/JPEG assets through Commons. Topic
article image associations help locate mechanism diagrams before falling back
to a broad Commons file search. Public HTML search markup is an experimental,
undocumented dependency, rather than the supported Brave Search API. Format
changes, HTTP failures and verification challenges stop that lookup; no challenge
bypass is attempted. Availability can change.

Fetched pages are data. Their scripts and instructions are not executed. The
fetcher validates public DNS addresses, pins the chosen address for the TLS
connection, preserves hostname verification, revalidates redirect destinations,
and bounds response sizes and redirect counts. It reads HTML/text sources;
PDF-only results are skipped by this adapter. Text is quoted from an opened
source page, not from a search snippet. Source/creator/license attribution is
retained; this does not establish independent factual, visual or rights review.

## Reproduce the continuous development probe

```bash
python3 -m presenter.researched_demo \
  --out-dir artifacts/a-new-researched-rehearsal \
  --asr-python .venv-asr/bin/python
python3 -m presenter.rehearsal_report artifacts/a-new-researched-rehearsal --video
```

Use a new directory for each attempt. Results and failed attempts are preserved.
The script makes about two minutes of local FFmpeg/libflite speech. It supplies
only the cooling-loop brief and notes for preparation; the future speech script
is withheld. It checks that heat-pipe, thermoelectric and sourdough terms are
absent from the completed preparation. It then feeds the audio at real pace
through the authenticated PCM endpoint, local tiny.en recognition, unattended
research worker and read-only stage observer. There are no manual stage changes
or injected online results during speech. Source outline approval in this probe
is a developer fixture, not independent presenter or editorial review.

The exported movie reconstructs measured stage API observations against the
actual audio. It is labeled as a reconstruction and synthetic speech. It is not
a browser screen recording, physical microphone test or projector latency
measurement. `result.json` retains ASR updates, request decisions, actual scene
changes, sources, timestamps and code fingerprints. `summary.json` checks topic
words in scene text/image descriptions; it does not score semantic correctness
or audience usefulness. Query strings are excluded from those lexical checks.

The first four frozen continuous attempts produced no automatic research
intervention. They exposed wasted lookup budget on ambiguous fragments, poor
context across speech windows, and conflation of candidate ranking with support.
Their original records and reconstructed videos are retained beside later repair
attempts. Successful isolated HTTP lookups do not erase those continuous failures.

The fifth repair attempt completed 114.6 seconds of synthetic audio. Preparation
took 3.33 seconds and added an online quotation and image to the supplied notes.
During speech, an unprepared heat-pipe question triggered unattended retrieval of
a Wikipedia explanation. It reached the stage API at 31.07 seconds, 12.51 seconds
after that segment began. That interval includes hearing the developing question;
it is not isolated provider or browser latency. The thermoelectric detour did not
produce a matching visual. No bread-related scene appeared during the unrelated
control, and prepared content was selected again. There were no operator stage
changes or injected search results during speech. Only one of the two related
detours received a matching new source; this remains an incomplete result.

The ASR worker processed 91 of 115 received windows, coalesced/dropped 24, recorded
four timeouts and one expiry. These overlapping windows are not independent
spoken sentences; counts do not estimate word accuracy. Stage/source observations
and all earlier failed attempts are retained in
`data/researched_rehearsal_pilot_v1.json`. The local watchable result is
`artifacts/researched_rehearsal_v5/index.html`, with a labeled MP4 reconstruction.

For a supplemental real-human recording condition, the same controller can run
against the pinned Sivers TED excerpt without supplying its transcript:

```bash
python3 -m presenter.researched_demo \
  --out-dir artifacts/a-new-sivers-rehearsal \
  --fixture-json data/researched_rehearsal_sivers_v1.json
python3 -m presenter.rehearsal_report artifacts/a-new-sivers-rehearsal --video
```

This talk was used in earlier development. Automatically researched preparation
may cover spoken subjects, so this fixture does not claim that every subject is
unprepared or that it is an independent held-out talk.

In the recorded condition, preparation research returned no usable source, so
the package contained only the supplied short notes. During 120 seconds of paced
TED audio, the worker discovered and opened
[Sivers' own first-follower article](https://sive.rs/ff) and selected its quotation
at 33.35 seconds. This was about 7.08 seconds after the first matching ASR update
completion estimate, excluding time to hear the cue and browser paint. The full
talk transcript was not supplied beforehand. There were no operator interventions
or injected results during speech. Only one fresh source intervention occurred;
later new phrases did not produce additional source changes. The worker processed
106 of 120 overlapping windows, dropped 14, and recorded two timeouts/two expiries.

The local comparison hub is `artifacts/researched_rehearsal/index.html`. It links
both current-controller movies and the four earlier failed synthetic attempts.
The movie reconstructs API observations, rather than recording the browser. This
is functional evidence of unattended retrieval during real recorded speech;
it is not proof that the visuals are useful enough to replace a prepared deck.

## Preparation conversation and validation limits

Automatic research currently works with the source-outline fallback. It adds
retrieved quotes and attributed images; that fallback does not reason through
the explanation or interpret free-form discussion. The existing conversational
preparation provider remains available when its account can run. In this session,
all four local Copilot account probes were quota-blocked. Claude had no active
login; the installed Gemini client's existing OAuth account returned an
unsupported-client eligibility error. No new provider credentials were created,
and none of these failed probes establishes conversational preparation success.

A convincing final acceptance test still needs a human presenter using the
actual browser/microphone/projector, unannounced questions, an independently
judged relevance/visual-quality record, and a comparison with prepared-only
operation. Repairing a known synthetic script can demonstrate functioning
integration, but cannot establish that broader acceptance result.
