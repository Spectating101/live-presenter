# Live explanation design

The product is a speech-directed explanation environment. Its unit of planning
is an audience question and the relationship that must become understandable.
Prepared and newly procured material can contribute to the same explanation.
A sequence of decorated text pages is insufficient.

The audience sees the visual itself, without webpage or operator chrome.
Automated development stays headless. Native motion and source-based comparison
are implemented in the separate output path described in `NATIVE_OUTPUT.md`.
Engagement matters alongside comprehension: expressive motion should make a
relationship or change easier to follow, and the system should adapt when the
speaker branches. Animation alone does not establish that adaptive ability.

## Evidence informing the design

These are research-informed defaults and explicit engineering interpretations,
not evidence that this app improves learning or that one presentation style is
universally best. Audience knowledge, task, material and accessibility matter.

| Research | Finding and scope | Product interpretation |
|---|---|---|
| [Moreno & Mayer (1999), *Cognitive principles of multimedia learning: The role of modality and contiguity*](https://doi.org/10.1037/0022-0663.91.2.358), [author-uploaded full paper](https://www.researchgate.net/profile/Richard-Mayer-4/publication/228698670_Cognitive_Principles_of_Multimedia_Learning_The_Role_of_Modality_and_Contiguity/links/57799c7608aead7ba0764344/Cognitive-Principles-of-Multimedia-Learning-The-Role-of-Modality-and-Contiguity.pdf) | Experiments on narrated scientific animations examined spatial proximity, timing and modality. Integrated verbal/visual material and concurrent narration supported learning in these settings. | Put short labels beside their referents and coordinate attention with the relevant speech. Keep captions and readable source text available for accessibility and explicit requests; do not turn a modality finding into a ban on text. |
| [Mautone & Mayer (2001), *Signaling as a cognitive guide in multimedia learning*](https://doi.org/10.1037/0022-0663.93.2.377), [author-provided paper record and abstract](https://www.researchgate.net/publication/232494695_Signaling_as_a_Cognitive_Guide_in_Multimedia_Learning) | Three experiments on an airplane-lift explanation tested organizational signals and transfer. Signaling helped in the tested conditions. | A cue should identify the relevant part or relationship, rather than attract attention arbitrarily. One focused annotation is our initial engineering choice, not a scientifically established numerical optimum. |
| [Mayer & Chandler (2001), *When learning is just a click away*](https://doi.org/10.1037/0022-0663.93.2.390), [full paper](https://tecfa.unige.ch/tecfa/teaching/methodo/Mayer_Chandler01.pdf) | Two experiments with narrated lightning explanations found transfer benefits for the tested learner-controlled pacing arrangements, without equivalent retention gains. | Support meaningful segments, Hold, revisiting and deliberate presenter control. Presenter-paced live delivery is a product adaptation; the paper did not test this agent or a live audience. |
| [Tversky, Morrison & Bétrancourt (2002), *Animation: can it facilitate?*](https://www.tc.columbia.edu/faculty/bt2158/faculty-profile/files/_Morrison_Betrancourt_AnimationCanitfacilitate.pdf) | This review argues that representations should match the concept and be perceptually comprehensible. Animation was not consistently superior to comparable static graphics; complexity, speed and unequal comparisons matter. | Match medium to meaning. Use motion for a relevant process or change; keep stable context and a static/reduced-motion alternative. Photorealism and continuous movement are not quality measures. |
| [Heer & Robertson (2007), *Animated transitions in statistical data graphics*](https://idl.uw.edu/papers/animated-transitions) | Two controlled experiments studied transitions between statistical graphics and found perceptual benefits for tested animation designs. | Preserve object correspondence when the representation changes. Keeping an image DOM node during a focus change is an implementation choice inspired by continuity, not a direct reproduction of those experiments. |

No seven-item working-memory rule, fixed audience attention span, learning-style
classification or inferred mental-state score is used. Current dwell times,
annotation counts and relevance thresholds are engineering bounds and need
evaluation; they are not psychological constants.

## Planning and live behavior

1. Establish the audience, intended takeaway, question and likely misconception.
2. Choose the representation needed to answer that question. A mechanism may
   need a cutaway; an observable social event may need footage with annotations;
   a quantitative comparison needs compatible, sourced measurements.
3. Reuse adequate prepared material. Direct attention within a stable visual
   before replacing it. Preserve essential context and source provenance.
4. For an unprepared question, procure the missing explanatory material in the
   background. Search for the required form as well as the topic. Verify what
   the asset actually shows and what interpretation the evidence supports.
5. Introduce a useful result while the explanation is still relevant and the
   presenter permits it. Keep weak, late or unsuitable results backstage.
   A found quotation can substantiate a claim without being the right visual.

For example, explaining a pump should focus the impeller within the loop.
A detour into heat pipes needs a grounded phase-change/capillary-return
representation. Another cooling photograph or a paragraph sharing the keyword
does not satisfy that request. In the Sivers example, original crowd footage
with clear identification of the first followers is a candidate explanatory
direction; its benefit still needs comparison with alternatives.

## Implemented in this increment

- Every newly validated concept has an explanation brief: audience question,
  provisional goal, preferred media and a planning rationale when supplied.
  The conversation prompt plans meaning before the current rendering options.
- `annotated_image` adds source-linked spatial attention targets to an existing
  imported image. Labels, target coordinates, cue phrases and source support
  enter the reviewed approval hash. They remain interpretations requiring visual
  review; exact quotations alone do not prove label meaning or placement.
- Prepared speech cues can focus an unambiguous target in the current image.
  The projector updates the annotation while preserving the image node. Manual
  Whole image/target controls remain available, including while held. Hold,
  stale-session rejection and bounded focus changes apply to automatic cues.
- Live research jobs include an explanation need. Public-web media discovery
  can request a mechanism diagram/map/chart rather than a generic topic image.
- Automatically retrieved quotations now stay backstage for ordinary explanatory
  requests. Explicit source-display requests retain progressive quote delivery.
  Images selected from metadata require semantic pixel verification before
  automatic display; existing metadata-only adapters do not provide it. A
  presenter can still explicitly choose a retrieved source/image.

Older stored jobs without an explanation brief retain legacy display behavior
for compatibility. New jobs always receive a brief; cache reuse is assessed
against the current brief, not the original request's display decision.

The current conversation provider receives image metadata, not pixels. It must
not guess annotation coordinates. This increment accepts explicitly supplied
coordinates and requires presenter review. It does not implement arbitrary new
cutaway generation, video procurement/playback, map rendering, a vision-based
asset reviewer, automatic annotation localization or validated audience modeling.
These missing capabilities must not be represented as completed by adding their
names to a procurement brief.

## How quality must be demonstrated

Use multiple talks and explanation types, including held-out topics and genuine
unprepared detours. Compare the same audio and content across the existing app,
the original presentation and candidate explanation designs. Keep timing and
available evidence comparable; a handcrafted reference is a design benchmark,
not an autonomous-system result.

Run counterbalanced or randomized audience comparisons, measure prior knowledge,
and use blinded scoring of comprehension and transfer to a new problem. Record
retention separately, including a delayed measure when feasible. Also record
incorrect or misleading visuals, distracting interruptions, coverage, recovery
and accessibility issues. Preference ratings are secondary to understanding.
Report uncertainty and failure cases; do not collapse this into a fabricated
single quality score or claim superiority from backend tests.

Browser checks can demonstrate stable imagery, readable labels and working
controls. Software checks can demonstrate provenance and authority boundaries.
Neither establishes the audience benefit. The first quality milestone is a
small, inspectable set of strong explanation examples, followed by the above
comparisons; the latency lane remains a separate measurement.
