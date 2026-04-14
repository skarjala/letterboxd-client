import unittest
from pathlib import Path

from letterboxd_client.parsers import (
    extract_form,
    parse_activity_page,
    parse_feed,
    parse_film,
    parse_list,
    parse_log_entry,
    parse_member,
)


FIXTURES = Path(__file__).with_name("fixtures")


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class ParserContractTests(unittest.TestCase):
    def test_extract_form_reads_first_form_and_inputs(self) -> None:
        action, values = extract_form(load_fixture("sign_in_form.html"))

        self.assertEqual(action, "/session/sign-in/")
        self.assertEqual(
            values,
            {
                "csrf": "abc123",
                "returnUrl": "/settings/",
                "username": "",
                "password": "",
            },
        )

    def test_parse_film_uses_json_ld_and_meta(self) -> None:
        film = parse_film("https://letterboxd.com/film/cure/", load_fixture("film.html"), lid="cure")

        self.assertEqual(film.id, "cure")
        self.assertEqual(film.title, "Cure")
        self.assertEqual(film.year, 1997)
        self.assertEqual(film.summary, "A hypnotic Japanese thriller.")
        self.assertEqual(film.stats["ratings"], 1234)
        self.assertEqual(film.stats["watched"], 567)
        self.assertEqual(film.raw["meta"]["og:title"], "Cure")

    def test_parse_member_uses_profile_meta(self) -> None:
        member = parse_member("https://letterboxd.com/sandeepkarjala/", load_fixture("member.html"), lid="sandeepkarjala")

        self.assertEqual(member.id, "sandeepkarjala")
        self.assertEqual(member.username, "sandeepkarjala")
        self.assertEqual(member.display_name, "Sandeep Karjala")
        self.assertEqual(member.bio, "Logging films for analysis.")
        self.assertEqual(member.stats["followers"], 321)
        self.assertEqual(member.stats["reviews"], 67)

    def test_parse_list_collects_film_links(self) -> None:
        list_resource = parse_list(
            "https://letterboxd.com/sandeepkarjala/list/top-japanese-thrillers/",
            load_fixture("list.html"),
            lid="top-japanese-thrillers",
        )

        self.assertEqual(list_resource.id, "top-japanese-thrillers")
        self.assertEqual(list_resource.title, "Top Japanese Thrillers")
        self.assertEqual(list_resource.description, "A compact list for parser tests.")
        self.assertEqual(len(list_resource.entries), 2)
        self.assertEqual(list_resource.entries[0].film.url, "https://letterboxd.com/film/cure/")
        self.assertEqual(list_resource.entries[1].film.url, "https://letterboxd.com/film/violence-and-vanity/")
        self.assertEqual(list_resource.stats["likes"], 8)

    def test_parse_activity_page_keeps_supported_link_types(self) -> None:
        page = parse_activity_page("https://letterboxd.com/sandeepkarjala/activity/", load_fixture("activity.html"))

        self.assertEqual(page.source_url, "https://letterboxd.com/sandeepkarjala/activity/")
        self.assertEqual([item.kind for item in page.items], ["film", "member", "list"])
        self.assertEqual([item.target for item in page.items], ["Cure", "Sandeep Karjala", "Top Japanese Thrillers"])

    def test_parse_log_entry_reads_review_and_comments(self) -> None:
        log_entry = parse_log_entry("https://letterboxd.com/log-entry/42/", load_fixture("log_entry.html"), lid="42")

        self.assertEqual(log_entry.id, "42")
        self.assertEqual(log_entry.film.url, "https://letterboxd.com/film/cure/")
        self.assertEqual(log_entry.review.text, "This is a concise review of Cure.")
        self.assertEqual(log_entry.stats["likes"], 12)
        self.assertEqual([comment.author for comment in log_entry.comments], ["Critic A", "Critic B"])
        self.assertEqual([comment.body for comment in log_entry.comments], ["Great review", "Strong take"])

    def test_parse_feed_reads_rss_items(self) -> None:
        page = parse_feed(load_fixture("feed.xml"))

        self.assertEqual(len(page.items), 2)
        self.assertEqual(page.items[0].kind, "film")
        self.assertEqual(page.items[0].target, "Cure was logged")
        self.assertEqual(page.items[0].summary, "Logged on a rainy evening.")
        self.assertEqual(page.items[1].kind, "list")
        self.assertEqual(page.items[1].target, "Sandeep updated a list")


if __name__ == "__main__":
    unittest.main()
