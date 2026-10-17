# Preparation-first studio

This is the new local product path in `presenter/`. It runs independently of the
missing historical v1–v10 checkpoint. It is a functional prototype; its browser
layout and physical microphone/projector behavior have not yet been verified.

```bash
make studio
```

Open the **complete access URL printed in your terminal**. The fragment carries
a local operator capability; the app removes it from the address bar after
opening. Keep that URL private. A bare loopback URL can load the interface but
cannot read or change your presentations. The server binds to `127.0.0.1` only.

Python 3.13 and a Unix-like host are currently supported (the single-writer lock
uses `fcntl`). No Python package installation is needed for the studio. PDF
import optionally needs `pdftotext`; scanned documents need OCR before import.
The existing historical `requirements.txt` is not required for this new path.

## Prepare the explanation

Create a presentation with an audience, purpose, and supplied source material.
Paste notes or attach UTF-8 TXT/Markdown/CSV/TSV, PDF, or DOCX. Limits are eight
distinct files, 4 MB per file, 100,000 extracted characters per file and 130,000
characters in one project. Source text is broken into stable quotable units;
CSV values are retained as a structured dataset.

Choose a preparation partner:

- **Conversation · Copilot** uses the machine's existing authenticated Copilot
  CLI (`copilot-spectator` by default). It receives the supplied material,
  brief and conversation. It has no tools available during preparation.
  `PRESENTER_COPILOT_COMMAND` can name another installed compatible CLI command.
  No OpenAI API integration or new API credential is required.
- **Source outline** extracts a reviewable outline without AI calls. It does
  not interpret free-form corrections. Edit the brief or switch to Conversation
  for a discussion. The worked example starts in this local mode deliberately.

The preparation partner proposes its understanding, source-linked concepts,
natural spoken aliases and visual alternatives. Discuss ambiguity, missing
evidence, scope or audience. Blocking questions prevent approval. Add further
material from the preparation view, or edit the brief and prepare again.
Failures keep the sources, discussion and prior draft; failed or outdated drafts
cannot be approved.

Six visual forms are implemented: explanation cards, flows, comparisons, exact
source metrics, CSV bar charts and evidence quotations. No model HTML/JavaScript
is executed. Charts read values directly from an existing numeric column. Charts
show at most 32 rows and explicitly label truncation. Source metrics must match
their exact displayed value in a supporting quote. Source quotes and IDs are
checked against the actual loaded text.

**Source linkage is not an automatic proof of a paraphrase or causal relation.**
Generated explanations and diagrams are labeled source-linked interpretations.
Review those interpretations against the displayed source support. Exact quotes
and numeric bindings receive structural checks; broader factual/semantic accuracy
still requires the preparation discussion and the presenter's review.

## Approve a particular version

Inspect the visual previews and source quotations. Resolve blocking questions,
then check “I reviewed the meaning, sources and visuals” and approve. This freezes
a separate visual package with source/package hashes and presenter approval.
New material, a changed brief, or another preparation message revokes approval.
Preparation cannot be edited during an active rehearsal; stop first.

## Rehearse and present

Open the projector, then start the rehearsal from the operator view. The projector
uses a separate read-only capability and receives approved material rather than
the private preparation conversation. It prepares every scene in the package
before displaying one. A double-click on the projector requests fullscreen.

You can type an utterance to rehearse or enable browser speech recognition.
Microphone use requires your click and browser permission. Support depends on the
browser/platform; Chromium may use an online speech service. Unsupported or
denied recognition leaves typed rehearsal available. Interim recognition text
does not change the stage.

The local follower matches prepared concepts and spoken aliases. Ambiguous or
unsupported speech retains the current visual. **Use Jev live advice** is an
explicit optional switch and starts off. When enabled, the current utterance and
approved context go to the existing Jev account. Jev may help choose among
locally supported approved ideas; it cannot create a scene or bypass approval,
stage hold or timing rules. Use `--no-jev` to disable that service entirely:

```bash
python3 -m presenter.server --no-jev
```

Use **Hold stage**, **Resume following**, **Next idea**, **Back**, or a prepared
visual thumbnail to take control. Stage changes have a 2.5-second minimum dwell.
**React to prepared cues · experimental** compiles a source-bound cue index and
uses a local path for clear cues. Ambiguity retains the stage or uses optional
Jev advice; presenter controls still apply. See `PREPARED_REFLEX.md` for measured
processing time and the distinction from microphone-to-projector latency.
Delayed recommendations cannot override a newer utterance or manual selection.
Repeated transcript sequence numbers are ignored. Starting a new rehearsal resets
the sequence and pending matches; manual controls clear pending automatic switches.
Up to ten completed rehearsal transcripts are retained privately in each project. The browser keeps a bounded
queue of recent final utterances rather than building a growing stale backlog.
Stopping or restarting the server returns the projector to standby; it never
automatically restarts the rehearsal.

No generative model creates new audience-visible content during this live path.
Off-script topics currently retain the stage and require further preparation.
The learned research policy remains separate and advisory; this prototype does
not claim to have earned empirical policy promotion.

## Persistence and privacy

Projects, extracted sources, discussions, drafts, approvals and rehearsal traces
are stored in the ignored `artifacts/studio/` directory. The directory is private
to the current OS user, project files use mode `0600`, and operator APIs require
the local access capability. The original uploaded file bytes are not retained;
the extracted source text and dataset values are retained. Back up that directory
if you need to preserve the workspace. Do not commit it.

Run one studio server per data directory. The server refuses a second writer.
Use a separate directory and port for another independent workspace:

```bash
python3 -m presenter.server --data-dir artifacts/other-studio --port 8766
```

This is a local single-user tool. It has no cloud collaboration, shared-account
identity system or production hosting deployment.

## Verification and current limits

`make verify` includes the existing research checks and product acceptance tests
for source ingestion, discussion/clarification, versioned approval, stage
selection, hold/resume, unknown topics, stale adviser results, interim/duplicate
transcripts, source metrics and CSV binding, read-only projector access,
operator authentication, single-writer persistence and restart behavior.

Real provider checks on the illustrative cooling-loop exercise:

1. Copilot prepared the explanation and visual alternatives from Markdown/CSV.
2. Asked whether High could be called most efficient, it identified missing
   temperature/heat-removal evidence and raised a blocking question.
3. The API rejected approval while that question remained unresolved.
4. After an explicit instruction to limit the claim to measured flow–power
   trade-offs, it removed the blocker and finalized a new package.
5. A typed rehearsal using the real Jev service selected the liquid flow, setting
   comparison and evidence for the measurement limit. An unrelated quantum-topic
   utterance held the current visual. The projector API matched each selection;
   presenter hold and stop also passed. This four-utterance development check is
   not an accuracy benchmark. Its advisory calls took approximately 194–207 ms.

Jev classifies the prepared idea and visual form in separate questions within one
request. Idea confidence is therefore not split across several valid visual
alternatives. The local support check includes the approved source quotations.
These thresholds remain provisional and need testing on independently edited talks.

Browser access to the local studio was declined by the browser tool during this
implementation. Browser interactions, layout, microphone permissions and physical
projector behavior are therefore **unverified**; JavaScript syntax and the HTTP/
data flow are checked independently. Physical microphone or visual rehearsal is
required before using this for a real presentation.

Matching is intentionally bounded by prepared concepts and cues. This is not a
claim of universal speech understanding or slide-deck replacement quality.
`RECORDED_TALKS.md` documents an actual bounded-audio replay and a synchronized
original-video comparison, including observed late transitions and visual gaps.
Images/video, mathematical typesetting, map/timeline renderers, fully local STT,
and audience evaluation remain future work. The separate 30-source research
tranche still needs independent editorial traces and source/context review.
