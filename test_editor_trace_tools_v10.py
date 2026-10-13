import unittest
from editor_trace_tools_v10 import build_prompt, causal_checkpoints, causal_windows, extract_json_rows, validate_editor_rows

SEG = [{"start_s": 0, "end_s": 10, "text": "Sales doubled."}, {"start_s": 10, "end_s": 20, "text": "Because pumps push water."},
       {"start_s": 20, "end_s": 30, "text": "Later we discuss funding."}]
CTX = {"has_dataset": True}
def row(**k): return {**{"start_s": 0, "end_s": 5, "function": "quantify", "representation": "chart", "confidence": .9}, **k}

class PromptTests(unittest.TestCase):
    def test_causal_hides_future(self):
        p = build_prompt(SEG, CTX, mode="causal", until_s=15)
        self.assertIn("pumps", p); self.assertNotIn("funding", p)
    def test_oracle_sees_all(self): self.assertIn("funding", build_prompt(SEG, CTX))
    def test_unavailable_flagged(self):
        lines = {l.split(":")[0].lstrip("- "): l for l in build_prompt(SEG, CTX).splitlines() if l.startswith("- ")}
        self.assertIn("NOT available", lines["evidence"]); self.assertNotIn("NOT available", lines["chart"])
    def test_bad_mode(self):
        with self.assertRaises(ValueError): build_prompt(SEG, CTX, mode="x")
        with self.assertRaises(ValueError): build_prompt(SEG, CTX, mode="causal")
    def test_checkpoints_end_at_talk_end(self):
        cps = list(causal_checkpoints(SEG, 15)); self.assertEqual(cps[0], 15); self.assertEqual(cps[-1], 30)

class WindowTests(unittest.TestCase):
    def test_windows_tile_talk_without_gaps(self):
        w = causal_windows(SEG, 10); self.assertEqual(w[0][0], 0); self.assertEqual(w[-1][1], 30)
        for a, b in zip(w, w[1:]): self.assertEqual(a[1], b[0])
    def test_window_prompt_restricts_start_and_hides_future(self):
        p = build_prompt(SEG, CTX, mode="causal", until_s=20, from_s=10)
        self.assertIn("START at or after 10.0s", p); self.assertIn("pumps", p); self.assertNotIn("funding", p)

class ValidateTests(unittest.TestCase):
    def test_good_row_kept(self):
        c, p = validate_editor_rows([row()], SEG, CTX); self.assertEqual((len(c), p), (1, []))
    def test_each_failure_dropped_and_reported(self):
        bad = [row(function="nope"), row(representation="evidence"), row(representation="zzz"), row(start_s=-1), row(end_s=99),
               row(start_s=4, end_s=5), row(confidence=2), {"start_s": "x"}]
        c, p = validate_editor_rows(bad, SEG, CTX); self.assertEqual((len(c), len(p)), (0, 8))
    def test_overlap_dropped(self):
        c, p = validate_editor_rows([row(), row(start_s=3, end_s=9)], SEG, CTX); self.assertEqual(len(c), 1); self.assertIn("overlaps", p[0])
    def test_extract_json(self):
        self.assertEqual(extract_json_rows('Sure!\n[{"a":1}]\nDone'), [{"a": 1}])
        with self.assertRaises(ValueError): extract_json_rows("no json")
if __name__ == "__main__": unittest.main()
