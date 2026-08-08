import unittest

from tools.manager_feed_discovery import (
    classify_vendor,
    extract_manager_entries,
    extract_official_website,
)


class ManagerFeedDiscoveryTest(unittest.TestCase):
    def test_extracts_manager_counts_and_skips_directory_pages(self):
        html = """
        <a href='/managers/alpha.html'>Alpha Management</a>
        12 buildings under management 7 managed rentals (7 no-fee)
        <a href='/managers/a_letter_managers.html'>Property managers filed under A</a>
        <a href='/managers/beta.html'>Beta Realty</a>
        3 buildings under management 1 brokered rental (1 no-fee)
        """
        rows = extract_manager_entries(html)
        self.assertEqual([row["manager_slug"] for row in rows], ["alpha", "beta"])
        self.assertEqual(rows[0]["buildings_managed"], 12)
        self.assertEqual(rows[0]["managed_rentals"], 7)
        self.assertEqual(rows[1]["brokered_rentals"], 1)

    def test_extracts_visible_official_domain_not_tracking_url(self):
        html = """
        <a href='https://www.nybits.com/nyc/nyb;jsessionid=abc?manager=alpha'>
            www.alpha-properties.com
        </a>
        <a href='https://www.hud.gov/other'>HUD</a>
        """
        website, candidates = extract_official_website(html, "https://www.nybits.com/managers/alpha.html")
        self.assertEqual(website, "https://www.alpha-properties.com")
        self.assertEqual(candidates[0], website)

    def test_classifies_only_known_public_vendor_markers(self):
        self.assertEqual(
            classify_vendor(["https://example.securecafe.com", "https://foo.appfolio.com"]),
            ["securecafe", "appfolio"],
        )
        self.assertEqual(classify_vendor(["https://example.com/about"]), [])


if __name__ == "__main__":
    unittest.main()
