import json, unittest
from pathlib import Path
from editor_trace_tools_v10 import validate_editor_rows
from transcript_io_v10 import parse_srt

D = Path(__file__).parent / "data" / "nasa_stgermain_cop26"
class PilotBundle(unittest.TestCase):
    def test_bundle_matches_source_and_validates(self):
        b = json.loads((D / "bundle.json").read_text(encoding="utf-8"))
        srt = parse_srt(D / "transcript.srt")
        self.assertEqual(len(b["transcript"]), len(srt)); self.assertEqual(b["transcript"][-1]["end_s"], srt[-1]["end"])
        for e in b["editors"]:
            clean, problems = validate_editor_rows(e["events"], b["transcript"], b["context"])
            self.assertEqual(problems, []); self.assertEqual(len(clean), len(e["events"]))
        self.assertTrue(b["metadata"]["pilot"] and b["metadata"]["license"] and b["metadata"]["source_uri"])
        self.assertFalse(b["metadata"]["independent_editors"])
if __name__ == "__main__": unittest.main()
