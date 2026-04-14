import unittest

from letterboxd_client.bulk import dedupe_by_lid, flatten_pages, hydrate_many, iterate_all
from letterboxd_client.models import Page


class BulkTests(unittest.TestCase):
    def test_flatten_pages(self) -> None:
        pages = [Page(items=[1, 2]), Page(items=[3])]
        self.assertEqual(flatten_pages(pages), [1, 2, 3])

    def test_iterate_all_uses_cursor(self) -> None:
        calls: list[str | None] = []

        def fake_call(*, cursor=None):
            calls.append(cursor)
            if cursor is None:
                return Page(items=[1, 2], next_cursor="next")
            return Page(items=[3], next_cursor=None)

        self.assertEqual(list(iterate_all(fake_call)), [1, 2, 3])
        self.assertEqual(calls, [None, "next"])

    def test_hydrate_many(self) -> None:
        self.assertEqual(hydrate_many(["a", "b"], lambda value: value.upper()), ["A", "B"])

    def test_dedupe_by_lid(self) -> None:
        rows = [{"id": "1", "title": "A"}, {"id": "1", "title": "A again"}, {"id": "2", "title": "B"}]
        self.assertEqual(dedupe_by_lid(rows), [rows[0], rows[2]])


if __name__ == "__main__":
    unittest.main()

