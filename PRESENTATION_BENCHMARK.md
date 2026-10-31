# Presentation benchmark: when edits show visuals and return to the speaker

The assistant supports a speaker; it does not replace one. Edited recordings of
strong live presentations show how professional editors divide attention between
the person and the presented material. This benchmark measures that division in
15 recordings across ten genres and scores the live stage against it.

The edit is one production team's judgment for a video audience. It is not a
recording of the room screen or a measure of comprehension. Wide shots can show a
projector screen for camera variety rather than as a decision to show it.

## Method

```bash
python3 -m venv .venv-media && .venv-media/bin/pip install yt-dlp
python3 -m presenter.edit_benchmark acquire            # 480p video, English captions, metadata
python3 -m presenter.edit_benchmark analyze --env-file /path/to/existing/credentials.env
python3 -m presenter.edit_benchmark summarize --out data/presentation_benchmark_results_v1.json
```

The catalog is `data/presentation_benchmark_v1.json`; media, captions, frames and
per-frame labels stay in ignored `artifacts/presentation_benchmark/`. FFmpeg scene
scores find cuts and slide changes (threshold 0.3). Each shot is sampled at least
every five seconds. Jev labels 512-pixel frames (Jev rejects images with a side
under 280 pixels) as speaker, speaker with object, board, full-screen visual,
stage with a projector screen, audience or other. Props and demonstrations count
as speaker time: a projector-side assistant cannot show them. "Content" is
full-screen visuals plus stage shots with a readable projector screen.

Jev images are an experimental TypeSafe feature, enabled per request with
`TypeSafe-Danger-Zone-Images: true`. All labels came from `jev-1.14.0`.

**Label check.** On 72 randomly sampled frames from two talks, labelled blind by
the development agent before reading Jev's labels, Jev agreed on speaker versus
content versus other for 71 (Rosling 47/48, Duarte 24/24). Its finer split between
speaker and speaker-with-object disagreed on 6 Rosling frames. This is one
reviewer, not an independent annotation study. Low-confidence label time is
reported for every recording; it is high (33–76%) for several YouTube recordings.

## Genre profiles

| Recording | Genre | Min | Content | Board | Speaker | Content episodes | Median episode s | Median return to speaker s |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Rosling, washing machine | TED balanced | 9 | 42% | 0% | 56% | 19 | 8.0 | 12.2 |
| Duarte, structure of talks | TED balanced | 18 | 56% | 0% | 44% | 45 | 10.6 | 9.8 |
| Gates, mosquitos | TED balanced | 20 | 26% | 0% | 72% | 16 | 14.7 | 47.3 |
| Rosling, best stats | TED visual-heavy | 20 | 76% | 0% | 24% | 36 | 13.5 | 4.8 |
| McCandless, data visualization | TED visual-heavy | 18 | 60% | 0% | 40% | 32 | 15.5 | 10.9 |
| Gore, climate | TED visual-heavy | 28 | 57% | 0% | 42% | 48 | 14.0 | 9.5 |
| Robinson, creativity | No-slide control | 19 | 2% | 0% | 96% | 5 | 3.8 | 85.9 |
| Jobs, iPhone 2007 | Product keynote | 105 | 71% | 0% | 27% | 178 | 12.2 | 4.9 |
| Winston, How to Speak | Lecture, slides and board | 64 | 11% | 39% | 49% | 40 | 9.6 | 11.1 |
| Lewin, pendulums | Lecture, demonstration | 48 | 0% | 70% | 27% | – | – | – |
| Royal Institution 2024 | Public science lecture | 59 | 25% | 4% | 55% | 151 | 4.4 | 7.9 |
| Pausch, Last Lecture | Inspirational lecture | 76 | 38% | 0% | 56% | 90 | 15.3 | 15.1 |
| McConnell, scientific presentations | Academic seminar | 42 | 100% | 0% | 0% | 1 | – | – |
| Strange Loop, concatenative | Technical conference | 40 | 98% | 0% | 1% | 6 | 20.5 | 8.7 |
| Rosling, 200 countries (BBC) | Data narration | 5 | 72% | 0% | 24% | 11 | 13.3 | 3.4 |

The control behaves as expected: a talk without slides is 2% content. Balanced
TED talks show content 26–56% of the time in episodes of roughly 8–15 seconds and
return to the speaker for 10–47 seconds. Visual-carried talks and the keynote
return only briefly (3–5 seconds). Lectures put much of their visual load on a
board. The seminar and conference recordings are fixed composite layouts (slide
and speaker share the frame throughout), so they contain no cut decisions; they
represent the persistent-visual style rather than a timing target.

These profiles imply one attention rule cannot serve every format. The engine
now has a `style` setting: `persist` keeps the previous slide-deck behavior and
`speaker_led` starts on the speaker and clears the screen once speech moves on.

## Scoring the stage

`python3 -m presenter.edit_benchmark compare --ids ID --replay RESULT.json`
compares a recorded replay's screen with the edit second by second and reports
agreement and Cohen's kappa against content time. The Rosling replay audio
aligns with the benchmark video within 0.02 seconds.

| Rosling, washing machine (frozen package, local reflex, tiny.en, latest-available audio) | Screen on | Kappa | Median visual s |
|---|---:|---:|---:|
| Edit | 42% | – | 8.0 |
| `persist` | 100% | 0.00 | 79.4 |
| `speaker_led`, topic-based release | 90% | 0.01 | 63.6 |

Topic support barely releases the screen: the prepared ideas are chapter-sized,
so nearly every sentence supports the visual already shown.

## Look or listen, from the words alone

`presenter/moment.py` asks Jev, for each caption cue and the two cues before it,
whether the moment calls for looking at something, listening to the speaker, or
is a transition. A causal hysteresis policy shows the screen when P(look) ≥ 0.5,
keeps it while later cues reach 0.3, and releases it six seconds after the last
such cue (minimum three seconds on, 0.5 s decision delay). The policy was chosen
on Rosling's washing-machine talk alone and frozen before scoring the others.

```bash
python3 -m presenter.moment --calibrate ted_rosling_washing_machine \
  --evaluate ted_duarte_structure ted_gates_mosquitos ... --env-file /path/to/credentials.env
```

| Recording | Role | Edit content | Screen on | Speaker time left clear | Kappa |
|---|---|---:|---:|---:|---:|
| Rosling, washing machine | calibration | 42% | 43% | 75% | 0.41 |
| Duarte | held out | 56% | 40% | 68% | 0.14 |
| Gates | held out | 26% | 35% | 69% | 0.12 |
| Gore | held out | 57% | 34% | 82% | 0.27 |
| McCandless | held out | 60% | 66% | 54% | 0.34 |
| Rosling, best stats | held out | 76% | 74% | 51% | 0.32 |
| Robinson (no slides) | held out | 2% | 8% | 92% | 0.06 |
| Jobs keynote | held out | 71% | 61% | 52% | 0.17 |
| Pausch | held out | 38% | 24% | 78% | 0.06 |
| Royal Institution | held out | 25% | 60% | 42% | 0.05 |
| Rosling, 200 countries | held out | 71% | 65% | 42% | 0.10 |
| Winston | held out | 11% | 38% | 65% | 0.16 |

Held-out kappa is positive on all eleven recordings but modest: median 0.14,
mean 0.16, compared with 0.00 for the existing persistent stage. The signal is
strongest on visual-heavy TED talks (0.27–0.34). It leaves the no-slide talk on
the speaker 92% of the time. It over-shows the Royal Institution lecture, whose
edit cuts quickly (4.4-second median episodes) between demonstrations and
slides, and Winston's lecture, whose visual load is mostly on a board.

What the words cannot supply is whether a visual exists. In these recordings
the edit follows the speaker's own deck; the assistant must also know whether it
has something worth showing. Captions are an upper bound: exact words with no
recognition errors or delay. The next steps are to drive the engine's
`speaker_led` release from this signal, combine it with the availability of a
prepared or retrieved visual, and repeat the evaluation on past-only speech
recognition windows; the live-stage section below does this. No audience or comprehension claim follows from these
agreement scores.

## The live stage

In `speaker_led` style the engine now asks Jev this same question on every
recognition window, with a 0.8-second limit. A visual appears only when the
words match a prepared visual and P(look) ≥ 0.5. It stays while P(look) ≥ 0.3
and returns to the speaker six seconds after the last such window, including
during a pause. At a "look" moment with no word match, Jev is also shown the
presenter's own visuals and may name one at confidence ≥ 0.85; see
[Without caption help](#without-caption-help). Jev cannot invent a visual, and Hold, Clear and
manual choices outrank it. If a call fails, that window follows prepared topics
instead (a six-second topic-based release).

`presenter.talk` ran each recording at real speed through local `tiny.en`, live
Jev and offscreen native output, using word matching alone. Results are in
`data/presentation_live_attention_v1.json`.

| Recording | Role | Edit content | Screen on | Speaker time left clear | Kappa | Edit full-screen episodes covered |
|---|---|---:|---:|---:|---:|---:|
| Rosling, washing machine (7 visuals) | policy chosen here | 42% | 33% | 78% | 0.27 | 6/16 |
| McCandless (17 visuals) | held out | 60% | 60% | 51% | 0.19 | 24/34 |

Across both runs, capture to decision took a median of about 0.87 seconds in the
final 120 windows of each (p95 1.23–1.31), Jev answered 96–98% of windows, and at most one
of 1,618 audio windows was dropped.

**The test favors the system in one way.** These decks are frames from the same
talks, cued with words from their captions. A speaker's own deck may match their
words less closely. Conditions also exclude a microphone, a room, a human
rehearsal and a physical projector. McCandless's visuals also run long (median
40 seconds, against 15.5 in the edit).

**A rejected setting.** A simulation on Rosling's recognition windows suggested
stricter values (0.6, 0.4, three seconds) with 35% screen time. Through the real
engine, which also requires a matching visual, they gave 10% screen time and kappa 0.10 on Rosling,
so the simulation was not a reliable guide and the original values were kept.
That setting's held-out McCandless run (kappa 0.23, 36% screen) scored higher,
but the choice was made on Rosling alone. Two talks cannot separate these settings.

## Without caption help

The table above overstates what word matching can do: its deck cues came from the
talk's own captions. A speaker's deck carries only what is printed on it. So each
talk was rerun with frames cued **only by OCR of the frame**, which on 480p video is
noisier than the clean text of a real PDF. Word matching alone then almost
stopped working: 0–3 visuals ever shown, kappa -0.08 to 0.09 across five talks.

Jev can look at the slides. Asked which of a talk's visuals the caption words
were about (up to 20 images per call, about 250 ms), on six talks:

| Confidence at least | Right slide, of 150 slide-time moments | Precision of picks in slide time | Picks in 147 speaker-time moments |
|---:|---:|---:|---:|
| none | 45 | 45/73 | 34 |
| 0.70 | 34 | 34/38 | 11 |
| 0.85 | 25 | 25/25 | 7 |
| 0.95 | 17 | 17/17 | 5 |

A speaker-time pick is not always wrong, because the camera can stay on someone
discussing a slide. The live stage uses 0.85. Twelve real-speed runs followed, four at a time, with results in
`data/presentation_rehearsal_v1.json`:

| Recording (minutes) | Role | Deck | Ever shown | Edit content | Screen on | Speaker left clear | Kappa |
|---|---|---:|---:|---:|---:|---:|---:|
| Rosling, washing machine (9) | held out | 12 | 4 | 42% | 23% | 83% | 0.16 |
| McCandless (18) | held out | 27 | 11 | 60% | 49% | 60% | 0.14 |
| Rosling, best stats (20) | held out | 20 | 9 | 76% | 60% | 53% | 0.15 |
| Winston (15) | held out | 2 | 1 | 2% | 1% | 99% | -0.02 |
| Rosling, 200 countries (5) | held out | 3 | 1 | 71% | 16% | 96% | 0.11 |
| Gore (20) | threshold set | 20 | 8 | 58% | 31% | 83% | 0.22 |
| Jobs keynote (15) | threshold set | 7 | 4 | 55% | 21% | 92% | 0.22 |
| Pausch (15) | threshold set | 17 | 4 | 42% | 8% | 94% | 0.04 |
| Duarte (18) | threshold set | 7 | 4 | 56% | 21% | 81% | 0.03 |
| Royal Institution (15) | threshold set | 11 | 2 | 29% | 6% | 95% | 0.02 |
| Gates (20) | threshold set | 14 | 4 | 26% | 12% | 88% | 0.00 |

**Control:** Robinson's no-slide talk with Gates's deck, 19 minutes: nothing shown.

The system now errs toward the speaker. It rarely shows a visual when it should
not, and it often misses one the edit showed. Kappa stays modest, and the edit is
one valid choice among many. Decision time rose under this load: the median from
capture to decision reached 1.5–1.8 seconds on the largest decks, and up to 25% of
audio windows expired. Alone, with the 27-visual deck, the median was 1.31 seconds
(p95 2.07).

**Did it pick the right slide at the right time?** Kappa cannot say, but each deck
image came from a known moment in its talk. A show counts as well timed when it
falls within 30 seconds of that moment. A later show may still be a fair callback, so
this is a lower bound. Three versions ran on all twelve recordings at real speed.
The rule was fixed before the last run: most well-timed shows on the threshold
talks, at least 60% accuracy, nothing on the wrong-deck control. Held-out talks
were reported and not used to choose.

| Version | Threshold talks: well timed | Held out: well timed | Held-out speaker left clear (median) | Wrong-deck control |
|---|---:|---:|---:|---:|
| **This window, 0.85 (kept)** | **27/38 (71%)** | 24/42 (57%) | 83% | nothing shown |
| About 20 s of words, 0.85, two windows agree | 21/30 (70%) | 18/30 (60%) | 96% | nothing shown |
| About 20 s of words, 0.70, two windows agree | 25/35 (71%) | 21/36 (58%) | 68% | nothing shown |

Offline, about 20 seconds of words doubled correct picks (25 to 52 of 150), and one
question per slide, the pattern in TypeSafe's Intelliprompter cookbook, did worse
than one question across all slides. Neither the extra words nor agreement between
windows improved real-speed accuracy, so the simplest version stayed. Differences of
this size on these samples are not strong evidence. Treat about 60–70% well-timed
as the current level, and offline scores as a poor predictor of live behavior.

**Virtual-display rehearsal.** A full run on a virtual X display used room-degraded
audio (band-limited, echo, pink noise) and real key events. It exposed two defects
that silenced speech for the rest of a talk, one after any key press and one after
a single late audio window; both are fixed. A failure drill cut Jev's network for
60 seconds, then killed the recognizer, then the audio source: the talk continued
on topics, restarted recognition, and ended cleanly with a report.

**Still untested:** a real person, a physical microphone in a room, a physical
projector, and choosing between two real displays. `arecord` delivered PipeWire
audio at real speed in a six-second check, separately from a full talk. No audience or
comprehension claim follows.

## Live news: how far it goes without a deck

News removes the prepared deck, so it tests finding something to show from speech
alone. Each run lasted 20 minutes at real speed, and DW's stream was also run as it
aired. Results are in `data/presentation_rehearsal_v1.json`. In the portions run,
editors showed content 35% (DW), 56% (PBS) and 80% (Crew-13) of the time. The mode
was designed and adjusted on these same recordings, so this is development evidence.

With the original lookup gates, nothing appeared in any run, for three reasons: the
"related to the talk" check rejects most news topics, automatic images required a
pixel check that never ran, and a few seconds of words rarely name a subject. So with
no deck, `presenter.talk --research` now uses an open-topic mode:

- Sensitivity replaces relevance. Nothing is looked up automatically while Jev judges
  the coverage sensitive (war, deaths, violence, disasters with victims and the like)
  at probability 0.2 or above.
- About 20 seconds of words name the topic, and the encyclopedia article is the source.
- Jev looks at up to five of the article's pictures, and the best must score at least
  0.85. In a check on 15 topics, wrong pictures from the right article scored as low as 0.07.
- Pictures carry an on-screen credit: "Archive image", artist, license, Wikimedia Commons.

| Recording | Mode | Shows | Screen on | Notes |
|---|---|---:|---:|---|
| DW, live as it aired | No deck | 1 | 2% | Wrong: a report cover. Document scans are now excluded, but that fix has not had its own live run |
| DW, earlier capture | No deck | 0 | 0% | Sensitive coverage stopped most lookups |
| PBS News Hour | No deck | 3 (2 subjects) | 3% | Netanyahu during an Israeli election story; World Series trophy during the parade story |
| Crew-13 coverage | No deck | 1 | 1% | A Dragon capsule, while Dragon was being discussed |
| Robinson (no slides) | No deck | 0 | 0% | False-alarm control: nothing shown |
| DW, earlier capture | Own graphics, OCR cues | 3 | 3% | Two graphics used, of 22 |
| PBS News Hour | Own graphics, OCR cues | 6 | 10% | Six graphics used, of 27 |

Speech to checked picture took about 3 seconds. No-deck runs lost at most 2 of 1,200
audio windows, including on the real live stream; the deck runs lost 10–17% with two
large decks running at once.

**What this shows.** The tool does not replace a news control room. Editors filled far
more of the airtime, largely with same-day footage and made-for-air graphics that no
encyclopedia holds. It mostly stays quiet rather than wrong: one false show in about
100 minutes of no-deck audio. It can add a relevant reference picture of a named
person, place or thing. An archive picture can still mislead in news, and the credit
reduces that risk without removing it. Treat this mode as experimental and do not use
it unattended on air. A rundown of a program's prepared graphics would likely do
better than OCR cues, but that is untested.

