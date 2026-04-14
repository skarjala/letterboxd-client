import json
import tempfile
import unittest
from pathlib import Path

from letterboxd_client.exports import to_jsonl
from letterboxd_client.models import Film


class JsonlTests(unittest.TestCase):
    def test_to_jsonl_returns_string(self) -> None:
        payload = to_jsonl([{"title": "Heat"}, {"title": "Thief"}])
        lines = payload.splitlines()
        self.assertEqual(json.loads(lines[0]), {"title": "Heat"})
        self.assertEqual(json.loads(lines[1]), {"title": "Thief"})

    def test_to_jsonl_writes_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "films.jsonl"
            to_jsonl([Film(id="1", title="Heat", url="https://example.com/heat")], path=path)
            written = path.read_text(encoding="utf-8").strip()

        self.assertEqual(json.loads(written)["title"], "Heat")


if __name__ == "__main__":
    unittest.main()
