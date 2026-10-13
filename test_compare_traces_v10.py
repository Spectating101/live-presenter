import unittest
from compare_traces_v10 import compare, match_events
def ev(a, b, f="explain", r="flow"): return {"start_s": a, "end_s": b, "function": f, "representation": r}

class T(unittest.TestCase):
    def test_identical(self):
        t = [ev(0, 10), ev(20, 30, "quantify", "chart")]
        m = compare(t, t, talk_s=40); self.assertEqual((m["recall"], m["precision"], m["both_agree_of_ref"], m["median_onset_lag_s"]), (1.0, 1.0, 1.0, 0.0))
    def test_late_and_wrong_representation(self):
        m = compare([ev(0, 10)], [ev(2, 10, r="chart")], talk_s=20)
        self.assertEqual((m["matched"], m["representation_agreement"], m["function_agreement"], m["median_onset_lag_s"]), (1, 0.0, 1.0, 2.0))
    def test_unmatched_and_extra(self):
        m = compare([ev(0, 10), ev(100, 110)], [ev(0, 10), ev(50, 60)], talk_s=120)
        self.assertEqual((m["matched"], m["recall"], m["precision"]), (1, 0.5, 0.5))
    def test_one_candidate_matches_once(self):
        self.assertEqual(len(match_events([ev(0, 10), ev(1, 9)], [ev(0, 10)])), 1)
    def test_empty(self):
        m = compare([], [], talk_s=10); self.assertIsNone(m["recall"])
if __name__ == "__main__": unittest.main()
