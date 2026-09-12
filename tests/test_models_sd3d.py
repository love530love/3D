import unittest

from models_sd3d import REGISTRY, screening_adapter
from model_screening import position_frequency_scores, ranked_numbers


class AdapterTests(unittest.TestCase):
    def test_adapter_returns_list_str_topk(self):
        adapter = screening_adapter("t_laplace", "test", position_frequency_scores)
        train = ["123", "124", "125", "223", "224", "225"] * 20
        preds = adapter.predict(train, 10)
        self.assertIsInstance(preds, list)
        self.assertEqual(len(preds), 10)
        for candidate in preds:
            self.assertIsInstance(candidate, str)
            self.assertEqual(len(candidate), 3)
            self.assertTrue(candidate.isdigit())

    def test_adapter_matches_screening_ranking(self):
        adapter = screening_adapter("t_pf", "test", position_frequency_scores)
        train = ["123", "124", "125", "223", "224", "225"] * 20
        self.assertEqual(
            adapter.predict(train, 10),
            ranked_numbers(position_frequency_scores(train))[:10],
        )

    def test_registry_expanded_with_battery(self):
        names = [spec.name for spec in REGISTRY]
        for expected in [
            "uniform_baseline",
            "position_frequency",
            "recent_position_frequency",
            "laplace_position_frequency",
            "recent_position_frequency_50",
            "recent_position_frequency_100",
            "recent_position_frequency_300",
            "markov_position_laplace",
        ]:
            self.assertIn(expected, names)

    def test_all_specs_expose_distribution(self):
        for spec in REGISTRY:
            self.assertIsNotNone(spec.distribution, f"{spec.name} missing distribution")


if __name__ == "__main__":
    unittest.main()
