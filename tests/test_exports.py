import tempfile
import unittest
import zipfile
from pathlib import Path

from letterboxd_client.exports import load_account_export_zip, normalize, parse_imdb_export, parse_letterboxd_csv


class ExportTests(unittest.TestCase):
    def test_parse_letterboxd_csv_normalizes_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "diary.csv"
            path.write_text("\ufeffName,Rating,,Rewatch\nHigh and Low,4.5,,Yes\n\n", encoding="utf-8")

            rows = parse_letterboxd_csv(path)

        self.assertEqual(rows[0]["name"], "High and Low")
        self.assertEqual(rows[0]["rating"], 4.5)
        self.assertEqual(rows[0]["rewatch"], True)
        self.assertEqual(len(rows), 1)

    def test_parse_imdb_export_handles_bom(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "imdb.csv"
            path.write_text("\ufeffTitle,Year\nAlien,1979\n", encoding="utf-8")
            rows = parse_imdb_export(path)

        self.assertEqual(rows, [{"title": "Alien", "year": 1979}])

    def test_load_account_export_zip_reads_csvs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "export.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("Diary Entries.csv", "Name,Rating\nAlien,5\n")
                zf.writestr("notes.txt", "ignore me")

            payload = load_account_export_zip(archive)

        self.assertIn("diary_entries", payload)
        self.assertEqual(payload["diary_entries"][0]["rating"], 5)

    def test_normalize_accepts_record_sequence(self) -> None:
        rows = normalize([{"Film Name": "Cure", "Liked": "true"}])
        self.assertEqual(rows, [{"film_name": "Cure", "liked": True}])


if __name__ == "__main__":
    unittest.main()
