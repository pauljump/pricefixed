import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tools.merges.build_complex_inventory import build_inventory


def create_listings_db(path):
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE listings (
            source TEXT, source_id TEXT, building_name TEXT, address TEXT,
            unit_number TEXT, PRIMARY KEY (source, source_id)
        );
    """)
    connection.executemany(
        "INSERT INTO listings VALUES (?,?,?,?,?)",
        [
            ("stuytown", "pcv-1", "Peter Cooper Village", "3 PETER COOPER ROAD", "10-A"),
            ("stuytown", "stuy-1", "Stuyvesant Town", "1 STUYVESANT OVAL", "01-B"),
            ("stuytown", "stuy-2", "Stuyvesant Town", "2 STUYVESANT OVAL", "02-C"),
        ],
    )
    connection.commit()
    connection.close()


def create_catalog_db(path):
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE addresses (
            normalized TEXT, bbl TEXT, address TEXT, zipcode TEXT
        );
        CREATE TABLE buildings (
            bbl TEXT, primary_address TEXT, units_res INTEGER, units_total INTEGER,
            building_class TEXT
        );
        CREATE TABLE units (bbl TEXT, unit_label TEXT);
        CREATE TABLE premises (
            premise_id TEXT, bbl TEXT, normalized TEXT, address TEXT
        );
        CREATE TABLE addressable_units (
            premise_id TEXT, unit_label TEXT, normalized_unit TEXT
        );
    """)
    connection.executemany(
        "INSERT INTO addresses VALUES (?,?,?,?)",
        [
            ("3 PETER COOPER RD", "1009780001", "3 PETER COOPER ROAD", "10010"),
            ("1 STUYVESANT OVAL", "1009720001", "1 STUYVESANT OVAL", "10009"),
            ("1 STUYVESANT OVAL", "1009990001", "1 STUYVESANT OVAL", "10009"),
            ("2 STUYVESANT OVAL", "1009720001", "2 STUYVESANT OVAL", "10009"),
        ],
    )
    connection.executemany(
        "INSERT INTO buildings VALUES (?,?,?,?,?)",
        [("1009780001", "342 1 AVENUE", 2491, 2498, "D6"),
         ("1009720001", "240 1 AVENUE", 8764, 8812, "D7"),
         ("1009990001", "1 STUYVESANT OVAL", 100, 100, "D6")],
    )
    connection.executemany(
        "INSERT INTO units VALUES (?,?)",
        [("1009780001", "10A"), ("1009720001", "01B")],
    )
    connection.executemany(
        "INSERT INTO premises VALUES (?,?,?,?)",
        [("p1", "1009780001", "3 PETER COOPER RD", "3 PETER COOPER ROAD"),
         ("p2", "1009720001", "1 STUYVESANT OVAL", "1 STUYVESANT OVAL")],
    )
    connection.executemany(
        "INSERT INTO addressable_units VALUES (?,?,?)",
        [("p1", "10A", "10A"), ("p2", "01B", "01B")],
    )
    connection.commit()
    connection.close()


class ComplexInventoryTest(unittest.TestCase):
    def test_preserves_address_evidence_and_property_resolution(self):
        with tempfile.TemporaryDirectory() as directory:
            listings = Path(directory) / "listings.db"
            catalog = Path(directory) / "catalog.db"
            create_listings_db(listings)
            create_catalog_db(catalog)
            report = build_inventory(listings, catalog)

        self.assertEqual(report["address_count"], 3)
        rows = {(row["property"], row["normalized_address"]): row for row in report["rows"]}
        peter = rows[("Peter Cooper Village", "3 PETER COOPER RD")]
        self.assertEqual(peter["resolved_bbl"], "1009780001")
        self.assertEqual(peter["exact_premise_unit_labels"], ["10A"])
        self.assertEqual(peter["direct_address_unit_labels"], ["10A"])
        self.assertEqual(peter["source_status"], "direct_address_evidence_multiple_sources")
        stuy = rows[("Stuyvesant Town", "1 STUYVESANT OVAL")]
        self.assertEqual(stuy["resolved_bbl"], "1009720001")
        self.assertEqual(stuy["resolution"], "property_anchor_disambiguation")


if __name__ == "__main__":
    unittest.main()
