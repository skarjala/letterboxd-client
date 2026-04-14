import unittest


class ImportSmokeTests(unittest.TestCase):
    def test_package_imports(self) -> None:
        import letterboxd_client

        self.assertTrue(hasattr(letterboxd_client, "LetterboxdClient"))

    def test_submodules_import(self) -> None:
        import letterboxd_client.bulk
        import letterboxd_client.exports

        self.assertTrue(hasattr(letterboxd_client.bulk, "iterate_all"))
        self.assertTrue(hasattr(letterboxd_client.exports, "to_jsonl"))


if __name__ == "__main__":
    unittest.main()

