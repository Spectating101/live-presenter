import asyncio, json, threading, unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from representation_policy_v10 import OracleRepresentationPolicy
from system1_v10 import (JevBackend, MockBackend, System1Assessor, System1Error, build_questions, parse_answers)

CTX = {"has_dataset": True, "has_sources": False}

class PolicyBugTests(unittest.TestCase):
    def test_zero_confidence_is_floored_not_promoted(self):
        p = OracleRepresentationPolicy.fit([{"function": "explain", "representation": "flow", "confidence": 0.0}])
        self.assertAlmostEqual(p.global_counts["flow"], 0.20)
    def test_missing_confidence_defaults_to_full(self):
        p = OracleRepresentationPolicy.fit([{"function": "explain", "representation": "flow"}])
        self.assertAlmostEqual(p.global_counts["flow"], 1.0)

class QuestionTests(unittest.TestCase):
    def test_unavailable_representations_not_offered(self):
        reps = build_questions(CTX)["representation_family"]["criteria"]
        self.assertIn("chart", reps); self.assertNotIn("evidence", reps); self.assertNotIn("media", reps)
    def test_parse_all_three_types(self):
        a = parse_answers({"a": {"type": "noul", "noul": .9},
                           "b": {"type": "choice", "choice": "x", "confidence": .8, "probabilities": {"x": .8, "y": .2}},
                           "c": {"type": "score", "score": 1.7, "confidence": .6, "legend": {}, "probabilities": {"1": 1.0}}})
        self.assertAlmostEqual(a["a"].confidence, .8); self.assertEqual(a["b"].value, "x"); self.assertEqual(a["c"].value, 1.7)
        with self.assertRaises(System1Error): parse_answers({"d": {"type": "wat"}})

class AssessorTests(unittest.IsolatedAsyncioTestCase):
    async def test_confident_answer(self):
        mock = MockBackend({"discourse_act": {"type": "choice", "choice": "quantify", "confidence": .9, "probabilities": {"quantify": .9}},
                            "representation_family": {"type": "choice", "choice": "chart", "confidence": .8, "probabilities": {"chart": .8}},
                            "topic_shift": {"type": "noul", "noul": .1}})
        a = await System1Assessor(mock).assess("sales doubled", current_topic="sales", context=CTX)
        self.assertEqual((a.act, a.representation, a.abstain, a.authority), ("quantify", "chart", False, "advisory_only"))
        self.assertEqual(len(mock.calls), 1)       # one batched call, five questions
        self.assertEqual(len(mock.calls[0][1]), 5)
    async def test_low_confidence_abstains(self):
        a = await System1Assessor(MockBackend()).assess("hmm", context=CTX)
        self.assertTrue(a.abstain)
    async def test_unavailable_pick_abstains(self):
        mock = MockBackend({"representation_family": {"type": "choice", "choice": "evidence", "confidence": .9, "probabilities": {"evidence": .9}},
                            "discourse_act": {"type": "choice", "choice": "explain", "confidence": .9, "probabilities": {"explain": .9}}})
        a = await System1Assessor(mock).assess("x", context=CTX)
        self.assertTrue(a.abstain); self.assertIn("unavailable", " ".join(a.reasons))
    async def test_backend_failure_falls_back_to_count_table(self):
        pol = OracleRepresentationPolicy.fit([{"function": "explain", "representation": "flow", "confidence": 1}] * 5)
        a = await System1Assessor(MockBackend(fail=True), fallback=pol).assess("x", context=CTX)
        self.assertEqual((a.source, a.representation, a.abstain, a.act), ("count_table", "flow", True, None))
    async def test_backend_failure_without_fallback(self):
        a = await System1Assessor(MockBackend(fail=True)).assess("x", context=CTX)
        self.assertEqual((a.source, a.representation, a.abstain), ("none", None, True))
    async def test_summary_tracks_agreement(self):
        pol = OracleRepresentationPolicy.fit([{"function": "quantify", "representation": "chart", "confidence": 1, "context": CTX}] * 5)
        mock = MockBackend({"discourse_act": {"type": "choice", "choice": "quantify", "confidence": .9, "probabilities": {"quantify": .9}},
                            "representation_family": {"type": "choice", "choice": "chart", "confidence": .9, "probabilities": {"chart": .9}}})
        s = System1Assessor(mock, fallback=pol); await s.assess("x", context=CTX)
        self.assertEqual(s.summary()["agreement_with_count_table"], 1.0)

class _Fake(BaseHTTPRequestHandler):
    seen = []
    def log_message(self, *a): pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Fake.seen.append((self.path, self.headers.get("Authorization"), body))
        if self.headers.get("Authorization") != "Bearer k": self.send_response(401); self.end_headers(); self.wfile.write(b"{}"); return
        ans = {n: ({"type": "noul", "noul": .7} if q["type"] == "noul" else
                   {"type": "choice", "choice": next(iter(q["criteria"])), "confidence": .9, "probabilities": {next(iter(q["criteria"])): .9}}
                   if q["type"] == "choice" else
                   {"type": "score", "score": 2.0, "confidence": .8, "legend": {}, "probabilities": {"2": .8}})
               for n, q in body["questions"].items()}
        out = json.dumps({"model": "jev-test", "answers": ans, "usage": {"input_tokens": 10, "output_tokens": 3}}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(out)

class JevClientTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.srv = HTTPServer(("127.0.0.1", 0), _Fake); _Fake.seen.clear()
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_port}"
    def tearDown(self): self.srv.shutdown(); self.srv.server_close()
    async def test_request_shape_and_parse(self):
        a = await System1Assessor(JevBackend("k", base_url=self.url)).assess("hello", current_topic="t", context=CTX)
        path, auth, body = _Fake.seen[0]
        self.assertEqual((path, auth, body["model"]), ("/v1/systemone", "Bearer k", "jev-latest"))
        self.assertEqual(set(body["questions"]), {"discourse_act", "topic_shift", "representation_family", "warm_now", "intervention_urgency"})
        self.assertEqual(body["state"]["current_topic"], "t")
        self.assertEqual((a.source, a.topic_shift, a.urgency), ("jev", .7, 2.0))
    async def test_auth_error_degrades(self):
        a = await System1Assessor(JevBackend("wrong", base_url=self.url)).assess("x", context=CTX)
        self.assertEqual(a.source, "none"); self.assertIn("401", a.error)
    async def test_unreachable_degrades(self):
        a = await System1Assessor(JevBackend("k", base_url="http://127.0.0.1:9", timeout_s=.5)).assess("x", context=CTX)
        self.assertTrue(a.abstain); self.assertIsNotNone(a.error)
    def test_missing_key(self):
        import os; os.environ.pop("JEV_API_KEY", None); os.environ.pop("TYPESAFE_API_KEY", None)
        with self.assertRaises(System1Error): JevBackend()

if __name__ == "__main__": unittest.main()
