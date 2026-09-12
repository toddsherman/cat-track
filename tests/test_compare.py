import unittest
import numpy as np
import pandas as pd

from cattrack.compare import score_rest, period_stats


def epochs(minutes=10):
    return pd.DataFrame({"valid": True, "rms_mg": 8.0, "posture_change_deg": 0.0},
                        index=pd.date_range("2026-08-31", periods=minutes*12, freq="5s"))


class RestScoringTests(unittest.TestCase):
    def test_short_quiet_period_is_not_sleep_like_rest(self):
        rest, bouts = score_rest(epochs(4))
        self.assertFalse(rest.any())
        self.assertEqual(bouts, [])

    def test_brief_movement_connects_bout_without_earning_rest(self):
        ep = epochs(10)
        ep.iloc[58:62, ep.columns.get_loc("rms_mg")] = 100
        rest, bouts = score_rest(ep)
        self.assertEqual(len(bouts), 1)
        self.assertEqual(rest.sum()*5, 580)
        self.assertFalse(rest[58:62].any())

    def test_missing_time_never_connects_short_rest_periods(self):
        ep = epochs(8)
        ep.iloc[47:49, ep.columns.get_loc("valid")] = False
        rest, bouts = score_rest(ep)
        self.assertFalse(rest.any())
        self.assertEqual(bouts, [])

    def test_recording_edge_activity_not_counted(self):
        ep = epochs(10)
        ep.iloc[:3, ep.columns.get_loc("rms_mg")] = 100
        ep.iloc[-3:, ep.columns.get_loc("rms_mg")] = 100
        rest, bouts = score_rest(ep)
        self.assertEqual(len(bouts), 1)
        self.assertEqual(rest.sum()*5, 570)
        self.assertFalse(rest[:3].any())
        self.assertFalse(rest[-3:].any())

    def test_period_denominator_uses_only_selected_valid_time(self):
        ep = epochs(10)
        ep["norm_sd_mg"] = 4.0
        ep["raw_enmo_mg"] = 2.0
        ep["sleep_like_rest"] = np.arange(len(ep)) < 60
        selected = np.arange(len(ep)) < 96
        stats = period_stats(ep, selected)
        self.assertAlmostEqual(stats["observed_hours"], 8/60)
        self.assertAlmostEqual(stats["rest_fraction"], 5/8)
        self.assertAlmostEqual(stats["rest_hours_observed"], 5/60)


if __name__ == "__main__":
    unittest.main()
