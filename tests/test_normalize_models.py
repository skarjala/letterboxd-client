import unittest

from letterboxd_client.models import Film, to_plain_data
from letterboxd_client.normalize import normalize_mapping, normalize_records


class NormalizeAndModelsTests(unittest.TestCase):
    def test_normalize_mapping_recurses_into_nested_values(self) -> None:
        row = {
            "Film Name": "Heat",
            "Metadata": {
                "Watched On": "2024-01-02",
                "Flags": ["yes", "no"],
                "Rank": "3",
            },
            "Tags": ("Crime", "Thriller"),
            "Empty": "",
        }

        normalized = normalize_mapping(row)

        self.assertEqual(
            normalized,
            {
                "film_name": "Heat",
                "metadata": {"watched_on": "2024-01-02", "flags": [True, False], "rank": 3},
                "tags": ["Crime", "Thriller"],
                "empty": None,
            },
        )

    def test_normalize_records_accepts_iterables(self) -> None:
        rows = normalize_records({"Film Name": "Heat"} for _ in range(1))

        self.assertEqual(rows, [{"film_name": "Heat"}])

    def test_to_plain_data_converts_nested_tuples(self) -> None:
        payload = {
            "films": (
                Film(id="1", title="Heat", url="https://example.com/heat"),
                Film(id="2", title="Thief", url="https://example.com/thief"),
            )
        }

        plain = to_plain_data(payload)

        self.assertEqual(plain["films"][0]["title"], "Heat")
        self.assertEqual(plain["films"][1]["title"], "Thief")


if __name__ == "__main__":
    unittest.main()
