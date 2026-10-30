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
during a pause. Jev cannot pick or invent a visual, and Hold, Clear and manual
choices outrank it. If a call fails, that window follows prepared topics
instead (a six-second topic-based release).

`presenter.talk` ran each recording at real speed through local `tiny.en`, live
Jev and offscreen native output. Results are in
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
