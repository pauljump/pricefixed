import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from pricefixed.catalog import Catalog, init_catalog_db
from pricefixed.catalog.core import _id
from pricefixed.core import init_db, upsert_listings
from pricefixed.engine.crosswalk import normalize_address


class CatalogSecureCafeCrosswalkTest(unittest.TestCase):
    def test_official_dob_crosswalk_resolves_browser_listing_and_is_linked(self):
        evidence = {
            "source": "dob_now_job_filings",
            "source_url": "https://data.cityofnewyork.us/resource/w9ak-ipjd.json?$where=house_no%3D%271065%27",
            "retrieved_at": "2026-08-09T03:21:56Z",
            "rows": [{
                "job_filing_number": "M00614645-I1",
                "house_no": "1065",
                "street_name": "2 AVENUE",
                "bbl": "1013307502",
            }],
        }
        raw = json.dumps({
            "bbl": "1013307502",
            "bbl_evidence": evidence,
            "availability_url": "https://aalto57.securecafe.com/onlineleasing/aalto57/availableunits.aspx",
            "official_url": "https://www.bozzuto.com/apartments-for-rent/ny/new-york/aalto57",
        })
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            catalog_path = directory / "catalog.db"
            listings_path = directory / "listings.db"
            conn = init_catalog_db(catalog_path)
            conn.execute(
                "INSERT INTO addresses (address_id,bbl,address,normalized,zipcode,source) VALUES (?,?,?,?,?,?)",
                (_id("addr", "1013307502", "1065 2 AVE"), "1013307502",
                 "1065 2 AVE", normalize_address("1065 2 AVE"), "10022", "dob_now_job_filings"),
            )
            conn.commit()
            conn.close()

            listings_conn = init_db(listings_path)
            upsert_listings(listings_conn, [{
                "source_id": "sc-aalto57-06F",
                "building_name": "Aalto57",
                "address": "1065 2 Ave",
                "unit_number": "06F",
                "bedrooms": 1,
                "bathrooms": 1,
                "price": 6450,
                "sqft": 705,
                "zipcode": "10022",
                "raw_json": raw,
            }], "securecafe")
            listings_conn.close()

            conn = init_catalog_db(catalog_path)
            result = Catalog(conn).import_listings_db(listings_path)
            unit_row = conn.execute(
                "SELECT bbl,unit_label FROM units WHERE normalized_unit='06F'"
            ).fetchone()
            evidence_row = conn.execute(
                "SELECT source,observation_kind FROM observations "
                "WHERE source='dob_now_job_filings'"
            ).fetchone()
            link_row = conn.execute(
                "SELECT role FROM entity_match_evidence"
            ).fetchone()
            conn.close()

        self.assertEqual(result["units"], 1)
        self.assertEqual(result["resolved_unit_observations"], 1)
        self.assertEqual(unit_row, ("1013307502", "06F"))
        self.assertEqual(evidence_row, ("dob_now_job_filings", "official_address_bbl_crosswalk"))
        self.assertEqual(link_row, ("official_address_bbl_crosswalk",))


if __name__ == "__main__":
    unittest.main()
