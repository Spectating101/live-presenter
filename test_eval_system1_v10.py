import json, unittest
from pathlib import Path
from eval_system1_v10 import DEFAULT_BUNDLE, DEFAULT_ORACLE, evaluate, events_from_assessments, decision_times
from system1_v10 import Answer, MockBackend, System1Assessor, System1Response

class SpyBackend:
    """Confident 'chart' on any text containing 'sales', else low urgency.  Records every state it was shown."""
    name = "spy"
    def __init__(self): self.seen = []; self.contexts = []
    async def ask(self, state, questions):
        self.seen.append(state["latest_utterance"])
        self.contexts.append(state.get("recent_context", ""))
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
        self.assertEqual(spy.seen, [s["text"] for s in BUNDLE["transcript"]])
        for i, past in enumerate(spy.contexts):
            self.assertEqual(past, " ".join(s["text"] for s in BUNDLE["transcript"][:i]))
    async def test_events_and_scoring(self):
        r = await evaluate(BUNDLE, ORACLE, System1Assessor(SpyBackend()))
        self.assertEqual([(round(e["start_s"], 3), e["end_s"], e["representation"]) for e in r["events"]], [(10.001, 20.0, "chart")])
        self.assertTrue(r["strictly_causal"])
        self.assertTrue(all(d["ready_s"] >= d["input_available_s"] for d in r["decisions"]))
    async def test_mock_default_makes_no_events(self):
        r = await evaluate(BUNDLE, ORACLE, System1Assessor(MockBackend())); self.assertEqual(r["events"], [])
    def test_abstain_and_short_events_dropped(self):
        from system1_v10 import Assessment
        mk = lambda ab, u: Assessment("x", "explain", .9, 0, "flow", .9, .9, u, ab, [], 1.0)
        seg = [{"start_s": 0, "end_s": 1, "text": ""}, {"start_s": 10, "end_s": 14, "text": ""}]
        self.assertEqual(events_from_assessments(seg, [mk(True, 3), mk(False, 3)]), [])  # final caption finishes after talk end

    def test_latency_queue_and_abstention_end_events(self):
        from system1_v10 import Assessment
        mk = lambda ab, ms: Assessment("x", "explain", .9, 0, "flow", .9, .9, 3, ab, [], ms)
        seg = [{"start_s": i, "end_s": i+1, "text": "x"} for i in range(4)]
        a = [mk(False, 1500), mk(True, 100), mk(False, 0), mk(False, 0)]
        self.assertEqual(decision_times(seg,a), [2.5, 2.6, 3.0, 4.0])
        events = events_from_assessments(seg,a)
        self.assertEqual([(e["start_s"],e["end_s"]) for e in events],[(2.5,2.6),(3.0,4.0)])

    async def test_empty_unordered_and_parallel_replay_rejected(self):
        for transcript in ([], list(reversed(BUNDLE["transcript"]))):
            with self.assertRaises(ValueError):
                await evaluate({**BUNDLE,"transcript":transcript}, ORACLE, System1Assessor(MockBackend()))
        with self.assertRaises(ValueError):
            await evaluate(BUNDLE, ORACLE, System1Assessor(MockBackend()), concurrency=8)

    async def test_all_failures_are_not_success(self):
        r = await evaluate(BUNDLE, ORACLE, System1Assessor(MockBackend(fail=True)))
        self.assertEqual(r["status"], "backend_failed")
    async def test_real_pilot_runs_with_mock(self):
        b = json.loads(Path(DEFAULT_BUNDLE).read_text()); o = json.loads(Path(DEFAULT_ORACLE).read_text())
        r = await evaluate(b, o, System1Assessor(MockBackend())); self.assertEqual(r["segments"], 106)
if __name__ == "__main__": unittest.main()
