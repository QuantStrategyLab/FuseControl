"""Slice 4(e): Summary counting paths verification.

Verify SUC-06 step 5 and SUC-07 step 3 summary timelines match the corrected
golden annotations per REVIEW-REPORT golden corrections.

Per PROMPT-FUSE1-P2F.md Slice 4(e).
"""

import unittest
from pathlib import Path
import sys
import json

# Add parent directories to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))


class TestSummaryCountingPaths(unittest.TestCase):
    """Verify summary-step counting timelines are internally consistent."""

    def setUp(self):
        """Load successor cases."""
        goldens_path = repo_root / 'goldens' / 'successor-cases.json'
        with open(goldens_path) as f:
            data = json.load(f)
            self.cases = data['cases']

    def test_suc06_step5_corrected_timeline(self):
        """SUC-06 step 5: Verify corrected timeline is present.

        Per REVIEW-REPORT Slice 1 golden correction: Counts 3-9 occur on
        January 8, 9, 12, 13, 14, 15, 16 of 2026 (7 sessions, skipping weekends).
        """
        suc06 = self.cases['SUC-06']
        step5 = suc06['steps'][4]  # 0-indexed

        # Verify corrected timeline per REVIEW-REPORT
        step5_note = step5['note']
        self.assertIn('Counts 3, 4, 5, 6, 7, 8, 9 occur on January 8, 9, 12, 13, 14, 15, 16',
                     step5_note,
                     "SUC-06 step 5 timeline must match corrected golden per Slice 1")

    def test_suc07_step3_corrected_timeline(self):
        """SUC-07 step 3: Verify corrected timeline is present.

        Per REVIEW-REPORT Slice 1 golden correction: Counts 6-10 occur on
        January 13, 14, 15, 16, 20 of 2026 (5 sessions, skipping weekend + holiday).
        """
        suc07 = self.cases['SUC-07']
        step3 = suc07['steps'][2]  # 0-indexed

        # Verify corrected timeline per REVIEW-REPORT
        step3_note = step3['note']
        self.assertIn('Counts 6, 7, 8, 9, 10 occur on January 13, 14, 15, 16, 20',
                     step3_note,
                     "SUC-07 step 3 timeline must match corrected golden per Slice 1")

        # Verify final clearing session
        final_session = step3['final_session']
        self.assertEqual(final_session, '2026-01-20',
                        "Final clearing session must be 2026-01-20 per corrected timeline")

    def test_timelines_skip_weekends_and_holidays(self):
        """Verify that the corrected timelines skip non-trading days.

        January 2026 calendar (synthetic):
        - Weekend: Saturdays/Sundays
        - Holiday: January 19 (synthetic)

        Both SUC-06 and SUC-07 timelines skip from January 16 to January 20
        (skipping 17-19: weekend + holiday).
        """
        suc06_note = self.cases['SUC-06']['steps'][4]['note']
        suc07_note = self.cases['SUC-07']['steps'][2]['note']

        # Both timelines should include January 16
        self.assertIn('16', suc06_note)
        self.assertIn('16', suc07_note)

        # Both should skip to January 20
        self.assertIn('20', suc07_note,
                     "SUC-07 timeline must skip to January 20 after 16")

        # Verify no mention of 17, 18, 19 (weekend + holiday)
        for day in ['17', '18', '19']:
            self.assertNotIn(day, suc06_note,
                           f"SUC-06 timeline should not include non-trading day {day}")


if __name__ == '__main__':
    unittest.main()
