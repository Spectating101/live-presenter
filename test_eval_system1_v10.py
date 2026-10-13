import json, unittest
from pathlib import Path
from eval_system1_v10 import DEFAULT_BUNDLE, DEFAULT_ORACLE, evaluate, events_from_assessments
from system1_v10 import Answer, MockBackend, System1Assessor, System1Response

class SpyBackend:
    """Confident 'chart' on any text containing 'sales', else low urgency.  Records every state it was shown."""
    name = "spy"
    def __init__(self): self.seen = []
    async def ask(self, state, questions):
        self.seen.append(state["latest_utterance"])
        hot = "sales" in state["latest_utterance"].split(" ")[-3:] or state["latest_utterance"].rstrip(".").endswith("sales")
        ch = lambda k: Answer("choice", k, .9, {k: .9})
        return System1Response("spy", "spy", {"discourse_act": ch("quantify"), "representation_family": ch("chart"),
            "topic_shift": Answer("noul", .1, .8), "warm_now": Answer("noul", .9, .8),
            "intervention_urgency": Answer("score", 3.0 if hot else 0.0, .9)}, 1.0)

BUNDLE = {"talk_id": "t", "context": {"has_dataset": True},
          "transcript": [{"start_s": 0, "end_s": 5, "text": "Intro."}, {"start_s": 5, "end_s": 10, "text": "Look at sales."},
                         {"start_s": 10, "end_s": 15, "text": "More sales."}, {"start_s": 15, "end_s": 20, "text": "Unrelated."}]}
ORACLE = [{"start_s": 5, "end_s": 15, "function": "quantify", "representation": "chart", "confidence": 1}]

class T(unittest.IsolatedAsyncioTestCase):
    async def test_never_sees_future_text(self):
        spy = SpyBackend(); await evaluate(BUNDLE, ORACLE, System1Assessor(spy))
        self.assertEqual(len(spy.seen), 4)
        for text in spy.seen:                     # call i sees at most segments[:i+1]; the longest is the full talk
            self.assertTrue(any(text == " ".join(s["text"] for s in BUNDLE["transcript"][:i + 1]) for i in range(4)))
        self.assertNotIn("Unrelated.", min(spy.seen, key=len))
    async def test_events_and_scoring(self):
        r = await evaluate(BUNDLE, ORACLE, System1Assessor(SpyBackend()))
        self.assertEqual([(e["start_s"], e["end_s"], e["representation"]) for e in r["events"]], [(5.0, 15.0, "chart")])
        self.assertEqual((r["vs_oracle"]["recall"], r["vs_oracle"]["both_agree_of_ref"]), (1.0, 1.0)); self.assertTrue(r["strictly_causal"])
    async def test_mock_default_makes_no_events(self):
        r = await evaluate(BUNDLE, ORACLE, System1Assessor(MockBackend())); self.assertEqual(r["events"], [])
    def test_abstain_and_short_events_dropped(self):
        from system1_v10 import Assessment
        mk = lambda ab, u: Assessment("x", "explain", .9, 0, "flow", .9, .9, u, ab, [], 1.0)
        seg = [{"start_s": 0, "end_s": 1, "text": ""}, {"start_s": 10, "end_s": 14, "text": ""}]
        self.assertEqual(events_from_assessments(seg, [mk(False, 3), mk(True, 3)]), [])   # 1 s too short; abstain dropped
    async def test_real_pilot_runs_with_mock(self):
        b = json.loads(Path(DEFAULT_BUNDLE).read_text()); o = json.loads(Path(DEFAULT_ORACLE).read_text())
        r = await evaluate(b, o, System1Assessor(MockBackend())); self.assertEqual(r["segments"], 106)
if __name__ == "__main__": unittest.main()
