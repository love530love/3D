import unittest

from probability_metrics import benjamini_hochberg, empirical_p_value


class ProbabilityMetricTests(unittest.TestCase):
    def test_bh_monotone_and_capped(self):
        adj = benjamini_hochberg([0.01, 0.02, 0.03, 0.5])
        self.assertEqual(len(adj), 4)
        for i in range(1, len(adj)):
            # Benjamini-Hochberg adjusted p-values are non-decreasing.
            self.assertGreaterEqual(adj[i], adj[i - 1])
        for value in adj:
            self.assertLessEqual(value, 1.0)

    def test_bh_empty(self):
        self.assertEqual(benjamini_hochberg([]), [])

    def test_empirical_p_extremes(self):
        samples = [0.0, 0.001, 0.002, 0.0, 0.001]
        # Observed is the maximum -> nothing in the bootstrap equals/exceeds it.
        self.assertAlmostEqual(empirical_p_value(samples, 0.005), (1 + 0) / (5 + 1))
        # Observed is the minimum -> all bootstrap samples exceed it.
        self.assertAlmostEqual(empirical_p_value(samples, -1.0), (1 + 5) / (5 + 1))


if __name__ == "__main__":
    unittest.main()
