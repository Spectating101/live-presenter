import tempfile, unittest
from pathlib import Path
from transcript_io_v10 import parse_srt, load_transcript

SRT = "1\n00:00:00,340 --> 00:00:03,920\nHi there.\n\n2\n00:01:04,600 --> 00:01:10,740\nTwo\nlines.\n\n"
class T(unittest.TestCase):
    def test_srt(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.srt"; p.write_text(SRT, encoding="utf-8")
            r = parse_srt(p); self.assertEqual(len(r), 2)
            self.assertEqual((r[0]["start"], r[0]["text"]), (0.34, "Hi there.")); self.assertEqual((r[1]["start"], r[1]["text"]), (64.6, "Two lines."))
            self.assertEqual(load_transcript(p), r)
if __name__ == "__main__": unittest.main()
