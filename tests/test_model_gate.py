import unittest

from model_gate import evaluate


class GateTests(unittest.TestCase):
    def test_gate_uses_each_challenger_own_logloss(self):
        probabilities = {
            "models": {
                "uniform_baseline": {"log_loss": 2.30},
                "uniform": {"log_loss": 2.30},
                "challenger_A": {"log_loss": 2.10},  # better than uniform
                "challenger_B": {"log_loss": 2.50},  # worse than uniform
            }
        }
        comparisons = {
            "comparisons_vs_uniform": {
                "challenger_A": {"bootstrap_95ci": [0.01, 0.05], "corrected_p": 0.01},
                "challenger_B": {"bootstrap_95ci": [0.01, 0.05], "corrected_p": 0.01},
            }
        }
        result = evaluate(comparisons, probabilities)
        by_name = {c["model"]: c for c in result["candidates"]}
        # Both have identical CI and corrected_p; only log-loss against the
        # (per-challenger) uniform baseline differs -> proves the gate no longer
        # uses a single hard-coded anchor for every challenger.
        self.assertTrue(by_name["challenger_A"]["qualifies_for_review"])
        self.assertFalse(by_name["challenger_B"]["qualifies_for_review"])

    def test_gate_requires_corrected_p_below_threshold(self):
        probabilities = {
            "models": {
                "uniform_baseline": {"log_loss": 2.30},
                "challenger_X": {"log_loss": 2.10},
            }
        }
        comparisons = {
            "comparisons_vs_uniform": {
                "challenger_X": {"bootstrap_95ci": [0.01, 0.05], "corrected_p": 0.20},
            }
        }
        result = evaluate(comparisons, probabilities)
        self.assertFalse(result["candidates"][0]["qualifies_for_review"])
        self.assertEqual(result["status"], "BASELINE_REQUIRED")


if __name__ == "__main__":
    unittest.main()
