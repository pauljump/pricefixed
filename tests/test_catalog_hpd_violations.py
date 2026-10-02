"""Offline regression tests for official HPD unit evidence."""
import os
import tempfile
import unittest
import zipfile

from pricefixed.catalog import Catalog, init_catalog_db
import pricefixed.catalog.core as catalog_core


class HpdViolationsImportTest(unittest.TestCase):
    def test_creates_only_dwelling_units_with_direct_bbls(self):
        rows = [
            {
                "violationid": "101", "boroid": "1", "block": "42", "lot": "7",
                "apartment": "APT 6B", "housenumber": "45", "streetname": "Wall Street",
                "zip": "10005", "inspectiondate": "2026-07-01T00:00:00.000",
                "violationstatus": "Open",
            },
            {
                "violationid": "102", "boroid": "1", "block": "42", "lot": "7",
                "apartment": "PUBLIC HALL", "housenumber": "45", "streetname": "Wall Street",
                "zip": "10005", "inspectiondate": "2026-07-02T00:00:00.000",
                "violationstatus": "Open",
            },
            {
                "violationid": "103", "boroid": "bad", "block": "42", "lot": "7",
                "apartment": "7A", "inspectiondate": "2026-07-03T00:00:00.000",
                "violationstatus": "Open",
            },
        ]
        original = catalog_core.socrata
        catalog_core.socrata = lambda *args, **kwargs: rows
        try:
            with tempfile.TemporaryDirectory() as directory:
                catalog = Catalog(init_catalog_db(os.path.join(directory, "catalog.db")))
                stats = catalog.import_hpd_violations(limit=10, boro=1)
                self.assertEqual(stats["hpd_units"], 1)
                self.assertEqual(stats["hpd_non_dwelling_observations"], 1)
                self.assertEqual(stats["hpd_unresolved_unit_observations"], 1)
                self.assertEqual(catalog.conn.execute("SELECT COUNT(*) FROM units").fetchone()[0], 1)
                status = catalog.conn.execute(
                    "SELECT status FROM entity_matches WHERE entity_type='unit' "
                    "AND observation_id IN (SELECT observation_id FROM observations WHERE source_ref='102')"
                ).fetchone()[0]
                self.assertEqual(status, "not_a_dwelling")
        finally:
            catalog_core.socrata = original

    def test_status_reports_evidenced_units_against_citywide_target(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Catalog(init_catalog_db(os.path.join(directory, "catalog.db")))
            catalog.conn.execute(
                "INSERT INTO units VALUES ('unit_1','1000000001','1A','1A','2026-01-01','2026-01-01')"
            )
            catalog.conn.execute(
                "INSERT INTO buildings (bbl, units_res, source, first_seen, last_seen) "
                "VALUES ('1000000001', 10, 'pluto', '2026-01-01', '2026-01-01')"
            )
            catalog.conn.commit()
            status = catalog.status()
            self.assertEqual(status["nyc_housing_stock_target"], 3_705_000)
            self.assertAlmostEqual(status["evidenced_unit_coverage"], 1 / 3_705_000)
            self.assertEqual(status["pluto_residential_unit_capacity"], 10)
            self.assertAlmostEqual(status["evidenced_unit_coverage_against_pluto"], 0.1)

    def test_ranks_capacity_gaps_without_creating_missing_units(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Catalog(init_catalog_db(os.path.join(directory, "catalog.db")))
            catalog.conn.executemany(
                "INSERT INTO buildings (bbl, borough, primary_address, units_res, source, first_seen, last_seen) VALUES (?,?,?,?,?,?,?)",
                [("1000000001", "MANHATTAN", "1 Test Street", 20, "pluto", "2026-01-01", "2026-01-01"),
                 ("1000000002", "MANHATTAN", "2 Test Street", 10, "pluto", "2026-01-01", "2026-01-01")],
            )
            catalog.conn.execute("INSERT INTO units VALUES ('unit_1','1000000001','1A','1A','2026-01-01','2026-01-01')")
            catalog.conn.commit()
            gaps = catalog.capacity_gaps(limit=2, borough=1)
            self.assertEqual(gaps[0]["bbl"], "1000000001")
            self.assertEqual(gaps[0]["unnamed_capacity"], 19)
            self.assertEqual(catalog.conn.execute("SELECT COUNT(*) FROM units").fetchone()[0], 1)

    def test_materializes_anonymous_capacity_slots_without_creating_units(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Catalog(init_catalog_db(os.path.join(directory, "catalog.db")))
            catalog.conn.execute(
                "INSERT INTO buildings (bbl, units_res, source, first_seen, last_seen) VALUES ('1000000001', 3, 'pluto', '2026-01-01', '2026-01-01')"
            )
            catalog.conn.commit()
            stats = catalog.materialize_capacity_slots()
            self.assertEqual(stats["pluto_residential_capacity"], 3)
            self.assertEqual(stats["anonymous_capacity_slots"], 3)
            self.assertEqual(catalog.conn.execute("SELECT COUNT(*) FROM units").fetchone()[0], 0)

    def test_resumes_capacity_slots_from_a_durable_bbl_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Catalog(init_catalog_db(os.path.join(directory, "catalog.db")))
            catalog.conn.executemany(
                "INSERT INTO buildings (bbl, units_res, source, first_seen, last_seen) VALUES (?,?,?,?,?)",
                [("1000000001", 2, "pluto", "2026-01-01", "2026-01-01"),
                 ("1000000002", 3, "pluto", "2026-01-01", "2026-01-01")],
            )
            catalog.conn.commit()
            first = catalog.materialize_capacity_slots(batch_size=1, batches=1)
            second = catalog.materialize_capacity_slots(batch_size=1, batches=2)
            self.assertEqual(first["anonymous_capacity_slots"], 2)
            self.assertEqual(second["anonymous_capacity_slots"], 5)
            self.assertTrue(second["capacity_complete"])
            self.assertEqual(catalog.status()["anonymous_capacity_slots"], 5)

    def test_keeps_same_unit_label_at_two_addresses_on_one_bbl_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Catalog(init_catalog_db(os.path.join(directory, "catalog.db")))
            catalog.conn.executemany(
                "INSERT INTO addresses VALUES (?,?,?,?,?,?)",
                [("addr_1", "1000000001", "3 Peter Cooper Road", "3 PETER COOPER RD", "10010", "nyc_pad"),
                 ("addr_2", "1000000001", "7 Peter Cooper Road", "7 PETER COOPER RD", "10010", "nyc_pad")],
            )
            for number, address in (("obs_1", "3 Peter Cooper Road"), ("obs_2", "7 Peter Cooper Road")):
                catalog.conn.execute(
                    "INSERT INTO observations (observation_id,source,source_ref,observed_at,observation_kind,address,unit_label,evidence_grade) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (number, "test", number, "2026-01-01", "listing", address, "1F", "source_document"),
                )
                catalog._match(number, "building", "1000000001", "resolved", 1.0, "test", "test")
            catalog.conn.commit()
            stats = catalog.derive_addressable_units(limit=10)
            self.assertEqual(stats["addressable_units_derived"], 2)
            self.assertEqual(catalog.conn.execute("SELECT COUNT(*) FROM addressable_units").fetchone()[0], 2)

    def test_imports_ose_str_snapshot_only_after_official_address_resolution(self):
        worksheet = '''<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
        <row r="1"><c r="A1" t="inlineStr"><is><t>Listing ID</t></is></c><c r="B1" t="inlineStr"><is><t>Building Address</t></is></c><c r="C1" t="inlineStr"><is><t>Apartment/Unit</t></is></c><c r="D1" t="inlineStr"><is><t>Zip Code</t></is></c></row>
        <row r="2"><c r="A2" t="inlineStr"><is><t>123</t></is></c><c r="B2" t="inlineStr"><is><t>10 West Street</t></is></c><c r="C2" t="inlineStr"><is><t>4A</t></is></c><c r="D2" t="inlineStr"><is><t>10001</t></is></c></row>
        </sheetData></worksheet>'''
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "str.xlsx")
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("xl/worksheets/sheet1.xml", worksheet)
            catalog = Catalog(init_catalog_db(os.path.join(directory, "catalog.db")))
            catalog.conn.execute("INSERT INTO addresses VALUES ('addr','1000000042','10 West Street','10 W ST','10001','pad')")
            catalog.conn.commit()
            stats = catalog.import_ose_str_snapshot(path, "2026-01-07")
            self.assertEqual(stats["ose_str_snapshot_units"], 1)
            self.assertEqual(catalog.conn.execute("SELECT normalized_unit FROM units").fetchone(), ("4A",))

    def test_keeps_condo_tax_lot_distinct_from_physical_units(self):
        rows = [
            {
                "unit_bbl": "1012345001", "condo_base_bbl": "1012345000",
                "condo_number": "1234", "condo_key": "11234",
                "condo_base_bbl_key": "10123450001234", "unit_designation": "4B",
                "floor_text": "4", "model": "CONDO", "geometry_type": "UNIT",
                "effective_tax_year": "2026",
            },
            {"unit_bbl": "not-a-bbl", "unit_designation": "5A"},
        ]
        original = catalog_core.socrata
        catalog_core.socrata = lambda *args, **kwargs: rows
        try:
            with tempfile.TemporaryDirectory() as directory:
                catalog = Catalog(init_catalog_db(os.path.join(directory, "catalog.db")))
                stats = catalog.import_condo_units(limit=10)
                self.assertEqual(stats["official_condo_unit_lots"], 1)
                self.assertEqual(stats["invalid_condo_rows"], 1)
                self.assertEqual(catalog.conn.execute("SELECT COUNT(*) FROM units").fetchone()[0], 0)
                link = catalog.conn.execute(
                    "SELECT status FROM official_unit_lot_links WHERE unit_lot_bbl='1012345001'"
                ).fetchone()[0]
                self.assertEqual(link, "unresolved")
        finally:
            catalog_core.socrata = original

    def test_imports_hpd_work_order_as_direct_unit_evidence(self):
        rows = [{
            "omoid": "500", "bbl": "1000000042", "apartment": "APT 3C",
            "housenumber": "10", "streetname": "West Street", "zip": "10001",
            "omocreatedate": "2026-07-01", "omostatusreason": "Open",
        }]
        original = catalog_core.socrata
        catalog_core.socrata = lambda *args, **kwargs: rows
        try:
            with tempfile.TemporaryDirectory() as directory:
                catalog = Catalog(init_catalog_db(os.path.join(directory, "catalog.db")))
                stats = catalog.import_hpd_omo_work_orders(limit=10, boro=1)
                self.assertEqual(stats["hpd_omo_units"], 1)
                observation = catalog.conn.execute(
                    "SELECT source, address, unit_label FROM observations"
                ).fetchone()
                self.assertEqual(observation, ("hpd_omo_work_orders", "10 West Street", "APT 3C"))
                match = catalog.conn.execute(
                    "SELECT status, method FROM entity_matches WHERE entity_type='unit'"
                ).fetchone()
                self.assertEqual(match, ("resolved", "official_bbl_and_unit_label"))
        finally:
            catalog_core.socrata = original

    def test_imports_acris_legal_as_direct_historic_unit_evidence(self):
        rows = [{
            "document_id": "202600000001", "borough": "1", "block": "42", "lot": "7",
            "street_number": "45", "street_name": "Wall Street", "unit": "8D",
            "property_type": "CONDO", "good_through_date": "2026-07-01",
        }]
        original = catalog_core.socrata
        catalog_core.socrata = lambda *args, **kwargs: rows
        try:
            with tempfile.TemporaryDirectory() as directory:
                catalog = Catalog(init_catalog_db(os.path.join(directory, "catalog.db")))
                catalog.conn.execute(
                    "INSERT INTO addresses VALUES ('addr','1000420007','45 Wall Street','45 WALL ST','10005','nyc_pad')"
                )
                catalog.conn.commit()
                stats = catalog.import_acris_property_legals(limit=10, boro=1)
                self.assertEqual(stats["acris_legal_units"], 1)
                self.assertEqual(stats["acris_legal_addressable_units"], 1)
                observation = catalog.conn.execute(
                    "SELECT source_ref, address, unit_label FROM observations"
                ).fetchone()
                self.assertTrue(observation[0].startswith("202600000001:1000420007:"))
                self.assertEqual(observation[1:], ("45 Wall Street", "8D"))
                self.assertEqual(catalog.conn.execute("SELECT COUNT(*) FROM addressable_units").fetchone()[0], 1)
        finally:
            catalog_core.socrata = original

    def test_imports_vayo_archive_as_secondary_evidence_without_placeholders(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = os.path.join(directory, "all_nyc_units.db")
            source = __import__("sqlite3").connect(source_path)
            source.execute(
                "CREATE TABLE all_nyc_units (unit_id TEXT PRIMARY KEY,bbl TEXT,address TEXT,zipcode TEXT,"
                "unit_number TEXT,is_placeholder INTEGER,source_systems TEXT,confidence_score REAL,"
                "borough TEXT,ownership_type TEXT,bldgclass TEXT,yearbuilt INTEGER,numfloors REAL)"
            )
            source.executemany(
                "INSERT INTO all_nyc_units VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [
                    ("a", "1000000042", "10 West Street", "10001", "4A", 0, "nybits", .8,
                     "MN", None, None, None, None),
                    ("b", "1000000042", "10 West Street", "10001", "UNIT UNKNOWN", 1, "nybits", .1,
                     "MN", None, None, None, None),
                    ("c", "1000000042", "10 West Street", "10001", "FINISHES", 0, "nybits", .1,
                     "MN", None, None, None, None),
                    ("d", "1000000042", "10 West Street", "10001", "6B", 0, "TEXT_MINED_ECB_VIOLATIONS", .6,
                     "MN", None, None, None, None),
                ],
            )
            source.commit()
            source.close()
            catalog = Catalog(init_catalog_db(os.path.join(directory, "catalog.db")))
            catalog.conn.execute(
                "INSERT INTO addresses VALUES ('addr','1000000042','10 West Street','10 W ST','10001','nyc_pad')"
            )
            catalog.conn.commit()
            stats = catalog.import_vayo_all_nyc_units(source_path, limit=10)
            self.assertEqual(stats["vayo_archive_rows"], 3)
            self.assertEqual(stats["vayo_archive_units"], 1)
            self.assertEqual(stats["vayo_archive_addressable_units"], 1)
            self.assertEqual(stats["vayo_archive_non_dwelling_rows"], 1)
            self.assertEqual(stats["vayo_archive_text_mined_rows"], 1)
            observation = catalog.conn.execute(
                "SELECT source,address,unit_label,evidence_grade FROM observations"
            ).fetchone()
            self.assertEqual(observation, (
                "vayo_all_nyc_units_archive", "10 West Street", "4A", "archived_secondary_source",
            ))
            self.assertEqual(catalog.conn.execute("SELECT COUNT(*) FROM units").fetchone()[0], 1)
            self.assertEqual(catalog.conn.execute("SELECT COUNT(*) FROM addressable_units").fetchone()[0], 1)
            self.assertEqual(catalog.conn.execute(
                "SELECT cursor_ref FROM archive_import_progress WHERE source='vayo_all_nyc_units_archive'"
            ).fetchone()[0], "d")

    def test_imports_vayo_streeteasy_history_only_after_exact_pad_resolution(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = os.path.join(directory, "se.db")
            source = __import__("sqlite3").connect(source_path)
            source.executescript(
                "CREATE TABLE buildings (slug TEXT PRIMARY KEY,url TEXT,address TEXT,status TEXT);"
                "CREATE TABLE unit_summary (id INTEGER PRIMARY KEY,building_slug TEXT,unit TEXT,listing_type TEXT,"
                "date TEXT,price TEXT,price_numeric REAL,status TEXT,beds TEXT,baths TEXT,sqft TEXT,sqft_numeric INTEGER,"
                "asking_price REAL,discount_pct REAL,scraped_at TEXT,availability TEXT);"
            )
            source.execute("INSERT INTO buildings VALUES ('ten-west','https://streeteasy.com/building/ten-west','10 West Street','ok')")
            source.execute(
                "INSERT INTO unit_summary VALUES (1,'ten-west','4A','sale','02/06/26','$900,000',900000,'Sold','1','1','700',700,900000,0,'2026-02-07','unavailable')"
            )
            source.commit()
            source.close()
            catalog = Catalog(init_catalog_db(os.path.join(directory, "catalog.db")))
            catalog.conn.execute(
                "INSERT INTO addresses VALUES ('addr','1000000042','10 West Street','10 W ST','10001','nyc_pad')"
            )
            catalog.conn.commit()
            stats = catalog.import_vayo_streeteasy_unit_summary(source_path, limit=10)
            self.assertEqual(stats["vayo_streeteasy_units"], 1)
            self.assertEqual(stats["vayo_streeteasy_addressable_units"], 1)
            observation = catalog.conn.execute(
                "SELECT address,unit_label,price FROM observations"
            ).fetchone()
            self.assertEqual(observation, ("10 West Street", "4A", 900000.0))
            self.assertEqual(catalog.conn.execute(
                "SELECT cursor_ref FROM archive_import_progress WHERE source='vayo_streeteasy_unit_summary_archive'"
            ).fetchone()[0], "1")

    def test_imports_vayo_elliman_history_with_sanitized_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = os.path.join(directory, "elliman.db")
            source = __import__("sqlite3").connect(source_path)
            source.execute(
                "CREATE TABLE listings (core_listing_id TEXT PRIMARY KEY,address TEXT,unit TEXT,zip TEXT,"
                "listing_status TEXT,listing_type TEXT,home_type TEXT,ownership_type TEXT,list_price REAL,"
                "close_price REAL,list_date TEXT,close_date TEXT,update_date TEXT,bedrooms REAL,bathrooms_total REAL,"
                "living_area_sqft REAL,year_built INTEGER,building_name TEXT,source_mls TEXT,fetched_at TEXT,"
                "listing_agent_email TEXT)"
            )
            source.execute(
                "INSERT INTO listings VALUES ('101','10 West Street 4A, New York, NY 10001',NULL,'10001',"
                "'Closed','Sale','Condo','Condo',950000,900000,'2026-01-01','2026-02-06',NULL,1,1,700,2000,"
                "'West','MLS','2026-02-07','agent@example.com')"
            )
            source.commit()
            source.close()
            catalog = Catalog(init_catalog_db(os.path.join(directory, "catalog.db")))
            catalog.conn.execute(
                "INSERT INTO addresses VALUES ('addr','1000000042','10 West Street','10 W ST','10001','nyc_pad')"
            )
            catalog.conn.commit()
            stats = catalog.import_vayo_elliman_mls_archive(source_path, limit=10)
            self.assertEqual(stats["vayo_elliman_units"], 1)
            self.assertEqual(stats["vayo_elliman_addressable_units"], 1)
            payload = catalog.conn.execute("SELECT payload FROM source_documents").fetchone()[0]
            self.assertNotIn("agent@example.com", payload)
            self.assertEqual(catalog.conn.execute(
                "SELECT cursor_ref FROM archive_import_progress WHERE source='vayo_elliman_mls_archive'"
            ).fetchone()[0], "101")

    def test_imports_vayo_corcoran_history_with_sanitized_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = os.path.join(directory, "corcoran.db")
            source = __import__("sqlite3").connect(source_path)
            source.execute(
                "CREATE TABLE listings (listing_id TEXT PRIMARY KEY,property_id TEXT,source_id TEXT,listing_status TEXT,"
                "transaction_type TEXT,listing_type TEXT,building_type TEXT,property_type TEXT,ownership TEXT,unit_type TEXT,"
                "address1 TEXT,address2 TEXT,zip_code TEXT,borough TEXT,neighborhood TEXT,price REAL,bedrooms REAL,bathrooms REAL,"
                "total_bathrooms REAL,square_footage REAL,closed_rented_date TEXT,detail_fetched INTEGER,fetched_at TEXT,agent_email TEXT)"
            )
            source.execute(
                "INSERT INTO listings VALUES ('101','p','s','Closed','sale','Condo','Condo','Condo','Condo',NULL,"
                "'10 West Street','4A','10001','Manhattan','West',900000,1,1,1,700,'2026-02-06',1,'2026-02-07','agent@example.com')"
            )
            source.commit()
            source.close()
            catalog = Catalog(init_catalog_db(os.path.join(directory, "catalog.db")))
            catalog.conn.execute(
                "INSERT INTO addresses VALUES ('addr','1000000042','10 West Street','10 W ST','10001','nyc_pad')"
            )
            catalog.conn.commit()
            stats = catalog.import_vayo_corcoran_archive(source_path, limit=10)
            self.assertEqual(stats["vayo_corcoran_units"], 1)
            self.assertEqual(stats["vayo_corcoran_addressable_units"], 1)
            payload = catalog.conn.execute("SELECT payload FROM source_documents").fetchone()[0]
            self.assertNotIn("agent@example.com", payload)
            self.assertEqual(catalog.conn.execute(
                "SELECT cursor_ref FROM archive_import_progress WHERE source='vayo_corcoran_archive'"
            ).fetchone()[0], "101")

    def test_acris_unit_lane_filters_to_source_rows_with_unit_labels(self):
        rows = [{
            "document_id": "202600000001", "borough": "1", "block": "42", "lot": "7",
            "street_number": "45", "street_name": "Wall Street", "unit": "8D",
            "property_type": "CONDO", "good_through_date": "2026-07-01",
        }]
        captured = {}
        original = catalog_core.socrata
        catalog_core.socrata = lambda *args, **kwargs: captured.update(kwargs) or rows
        try:
            with tempfile.TemporaryDirectory() as directory:
                catalog = Catalog(init_catalog_db(os.path.join(directory, "catalog.db")))
                stats = catalog.import_acris_unit_legals(limit=10, boro=1)
                self.assertEqual(stats["acris_legal_units"], 1)
                self.assertIn("unit IS NOT NULL", captured["where"])
                self.assertIn("borough='1'", captured["where"])
        finally:
            catalog_core.socrata = original

    def test_acris_keeps_sibling_unit_labels_under_one_document_and_bbl(self):
        rows = [
            {
                "document_id": "202600000001", "borough": "1", "block": "42", "lot": "7",
                "street_number": "45", "street_name": "Wall Street", "unit": unit,
                "property_type": "CONDO", "good_through_date": "2026-07-01",
            }
            for unit in ("8D", "8E")
        ]
        original = catalog_core.socrata
        catalog_core.socrata = lambda *args, **kwargs: rows
        try:
            with tempfile.TemporaryDirectory() as directory:
                catalog = Catalog(init_catalog_db(os.path.join(directory, "catalog.db")))
                catalog.import_acris_unit_legals(limit=10, boro=1)
                self.assertEqual(catalog.conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0], 2)
                self.assertEqual(catalog.conn.execute("SELECT COUNT(*) FROM units").fetchone()[0], 2)
        finally:
            catalog_core.socrata = original

    def test_acris_unit_keyset_uses_inclusive_document_cursor(self):
        rows = [{
            "document_id": "202600000001", "borough": "1", "block": "42", "lot": "7",
            "street_number": "45", "street_name": "Wall Street", "unit": "8D",
            "property_type": "CONDO", "good_through_date": "2026-07-01",
        }]
        captured = {}
        original = catalog_core.socrata
        catalog_core.socrata = lambda *args, **kwargs: captured.update(kwargs) or rows
        try:
            with tempfile.TemporaryDirectory() as directory:
                catalog = Catalog(init_catalog_db(os.path.join(directory, "catalog.db")))
                stats = catalog.import_acris_unit_legals(
                    limit=10, boro=1, before_document_id="202600000010"
                )
                self.assertIn("document_id <= '202600000010'", captured["where"])
                self.assertEqual(stats["acris_legal_next_document_id"], "202600000001")
        finally:
            catalog_core.socrata = original

    def test_imports_annualized_sale_as_dated_unit_evidence(self):
        rows = [{
            "borough": "1", "block": "172", "lot": "1490", "bbl": "1001727504",
            "address": "50 FRANKLIN STREET, S9B", "apartment_number": "S9B", "zip_code": "10013",
            "sale_price": "1590000", "sale_date": "2019-06-21T00:00:00.000",
            "building_class_category": "10 COOPS - ELEVATOR APARTMENTS",
        }]
        original = catalog_core.socrata
        catalog_core.socrata = lambda *args, **kwargs: rows
        try:
            with tempfile.TemporaryDirectory() as directory:
                catalog = Catalog(init_catalog_db(os.path.join(directory, "catalog.db")))
                stats = catalog.import_annualized_sales(limit=10, boro=1)
                self.assertEqual(stats["annualized_sale_units"], 1)
                observation = catalog.conn.execute(
                    "SELECT address, unit_label, price, observed_at FROM observations"
                ).fetchone()
                self.assertEqual(observation, ("50 FRANKLIN STREET", "S9B", 1590000.0, "2019-06-21"))
        finally:
            catalog_core.socrata = original

    def test_imports_annualized_sale_unit_embedded_in_address(self):
        rows = [{
            "borough": "1", "block": "172", "lot": "1490", "bbl": "1001727504",
            "address": "50 FRANKLIN STREET, S9B", "apartment_number": None, "zip_code": "10013",
            "sale_price": "1590000", "sale_date": "2019-06-21T00:00:00.000",
            "building_class_category": "10 COOPS - ELEVATOR APARTMENTS",
        }]
        original = catalog_core.socrata
        catalog_core.socrata = lambda *args, **kwargs: rows
        try:
            with tempfile.TemporaryDirectory() as directory:
                catalog = Catalog(init_catalog_db(os.path.join(directory, "catalog.db")))
                stats = catalog.import_annualized_sales(limit=10, boro=1)
                self.assertEqual(stats["annualized_sale_units"], 1)
                self.assertEqual(catalog.conn.execute(
                    "SELECT address, unit_label FROM observations"
                ).fetchone(), ("50 FRANKLIN STREET", "S9B"))
                self.assertEqual(catalog.conn.execute(
                    "SELECT method FROM entity_matches WHERE entity_type='unit'"
                ).fetchone()[0], "official_bbl_and_address_unit_label")
        finally:
            catalog_core.socrata = original

    def test_imports_rolling_sale_with_constructed_bbl(self):
        rows = [{
            "borough": "2", "block": "172", "lot": "1490",
            "address": "50 FRANKLIN STREET", "apartment_number": "9B", "zip_code": "10451",
            "sale_price": "1590000", "sale_date": "2026-07-21T00:00:00.000",
            "building_class_category": "10 COOPS - ELEVATOR APARTMENTS",
        }]
        original = catalog_core.socrata
        catalog_core.socrata = lambda dataset, *args, **kwargs: rows
        try:
            with tempfile.TemporaryDirectory() as directory:
                catalog = Catalog(init_catalog_db(os.path.join(directory, "catalog.db")))
                stats = catalog.import_rolling_sales(limit=10, boro=2)
                self.assertEqual(stats["rolling_sale_units"], 1)
                self.assertEqual(catalog.conn.execute(
                    "SELECT bbl, normalized_unit FROM units"
                ).fetchone(), ("2001721490", "9B"))
        finally:
            catalog_core.socrata = original

    def test_imports_hpd_problem_without_creating_buildingwide_unit(self):
        rows = [
            {"problem_id": "1", "received_date": "2026-07-01", "borough": "MANHATTAN",
             "bbl": "1000000042", "house_number": "10", "street_name": "West Street",
             "apartment": "3C", "problem_status": "Open"},
            {"problem_id": "2", "received_date": "2026-07-02", "borough": "MANHATTAN",
             "bbl": "1000000042", "house_number": "10", "street_name": "West Street",
             "apartment": "BLDG", "problem_status": "Open"},
        ]
        original = catalog_core.socrata
        catalog_core.socrata = lambda *args, **kwargs: rows
        try:
            with tempfile.TemporaryDirectory() as directory:
                catalog = Catalog(init_catalog_db(os.path.join(directory, "catalog.db")))
                stats = catalog.import_hpd_problems(limit=10, boro=1)
                self.assertEqual(stats["hpd_problem_units"], 1)
                self.assertEqual(stats["hpd_problem_non_dwelling"], 1)
        finally:
            catalog_core.socrata = original

    def test_imports_nycha_inspected_unit_with_official_bbl(self):
        rows = [{
            "viol_seq_no": "7", "boro": "1", "bbl": "1000000042", "phn": "10",
            "str_nm": "West Street", "actl_unit_insp": "A-12", "insp_dt": "2026-07-01",
            "hzrd_clas": "Class B", "issued_in_err": "N",
        }]
        original = catalog_core.socrata
        catalog_core.socrata = lambda *args, **kwargs: rows
        try:
            with tempfile.TemporaryDirectory() as directory:
                catalog = Catalog(init_catalog_db(os.path.join(directory, "catalog.db")))
                stats = catalog.import_nycha_hmc_violations(limit=10, boro=1)
                self.assertEqual(stats["nycha_hmc_units"], 1)
                self.assertEqual(catalog.conn.execute(
                    "SELECT source, unit_label FROM observations"
                ).fetchone(), ("nycha_hmc_violations", "A-12"))
        finally:
            catalog_core.socrata = original

    def test_imports_residential_eviction_without_marshal_names(self):
        rows = [{
            "court_index_number": "1", "docket_number": "2", "eviction_address": "10 West Street",
            "eviction_apt_num": "3C", "executed_date": "2026-07-01", "residential_commercial_ind": "Residential",
            "borough": "MANHATTAN", "eviction_zip": "10001", "eviction_possession": "Possession",
            "ejectment": "Not an Ejectment", "bbl": "1000000042",
        }]
        original = catalog_core.socrata
        catalog_core.socrata = lambda *args, **kwargs: rows
        try:
            with tempfile.TemporaryDirectory() as directory:
                catalog = Catalog(init_catalog_db(os.path.join(directory, "catalog.db")))
                stats = catalog.import_evictions(limit=10, boro=1)
                self.assertEqual(stats["eviction_units"], 1)
                payload = catalog.conn.execute("SELECT payload FROM source_documents").fetchone()[0]
                self.assertNotIn("marshal", payload.lower())
                observation = catalog.conn.execute(
                    "SELECT address, unit_label, status FROM observations"
                ).fetchone()
                self.assertEqual(observation, ("10 West Street", "3C", "Possession / Not an Ejectment"))
        finally:
            catalog_core.socrata = original

    def test_imports_each_dob_job_apartment_label(self):
        rows = [{
            "job_filing_number": "M01234567", "bbl": "1000000042", "house_no": "10",
            "street_name": "West Street", "apt_condo_no_s": "2A, 2B", "filing_date": "2026-07-01",
            "filing_status": "Approved", "postcode": "10001",
        }]
        original = catalog_core.socrata
        catalog_core.socrata = lambda *args, **kwargs: rows
        try:
            with tempfile.TemporaryDirectory() as directory:
                catalog = Catalog(init_catalog_db(os.path.join(directory, "catalog.db")))
                stats = catalog.import_dob_now_jobs(limit=10, boro=1)
                self.assertEqual(stats["dob_job_units"], 2)
                labels = catalog.conn.execute(
                    "SELECT unit_label FROM observations ORDER BY unit_label"
                ).fetchall()
                self.assertEqual(labels, [("2A",), ("2B",)])
        finally:
            catalog_core.socrata = original

    def test_imports_each_dob_approved_permit_apartment_label(self):
        rows = [{
            "job_filing_number": "M01234567", "work_permit": "M01234567-I1", "bbl": "1000000042",
            "house_no": "10", "street_name": "West Street", "apt_condo_no_s": "2A / 2B",
            "issued_date": "2026-07-01", "permit_status": "Issued", "zip_code": "10001",
        }]
        original = catalog_core.socrata
        catalog_core.socrata = lambda *args, **kwargs: rows
        try:
            with tempfile.TemporaryDirectory() as directory:
                catalog = Catalog(init_catalog_db(os.path.join(directory, "catalog.db")))
                stats = catalog.import_dob_now_permits(limit=10, boro=1)
                self.assertEqual(stats["dob_permit_units"], 2)
                observation = catalog.conn.execute(
                    "SELECT source, observation_kind, status FROM observations LIMIT 1"
                ).fetchone()
                self.assertEqual(observation, ("dob_now_approved_permits", "official_approved_permit", "Issued"))
        finally:
            catalog_core.socrata = original

    def test_captures_hpd_registration_coverage_without_claiming_completeness(self):
        rows = [{
            "registrationid": "99", "buildingid": "88", "boroid": "1", "block": "42", "lot": "7",
            "housenumber": "45", "streetname": "Wall Street", "zip": "10005",
            "registrationenddate": "2030-01-01",
        }]
        original = catalog_core.socrata
        catalog_core.socrata = lambda *args, **kwargs: rows
        try:
            with tempfile.TemporaryDirectory() as directory:
                catalog = Catalog(init_catalog_db(os.path.join(directory, "catalog.db")))
                catalog.conn.execute(
                    "INSERT INTO buildings VALUES ('1000420007','MANHATTAN','45 Wall Street','10005',10,10,'D4','test','2026-01-01','2026-01-01')"
                )
                catalog.conn.commit()
                stats = catalog.import_hpd_registration_coverage(limit=10, boro=1)
                self.assertEqual(stats["coverage_status"], "partial")
                coverage = catalog.conn.execute(
                    "SELECT membership_status, pluto_units_res, canonical_unit_labels FROM building_coverage"
                ).fetchone()
                self.assertEqual(coverage, ("hpd_unexpired_pluto_residential", 10, 0))
        finally:
            catalog_core.socrata = original

    def test_imports_pad_addresses_without_creating_units(self):
        original = catalog_core.build_crosswalk_pad

        def fake_pad(conn, zips, limit=None):
            conn.execute(
                "CREATE TABLE crosswalk (norm_address TEXT, bbl TEXT, borough TEXT, zipcode TEXT)"
            )
            conn.execute(
                "INSERT INTO crosswalk VALUES ('45 WALL ST', '1000000001', 'MANHATTAN', '10005')"
            )
            conn.commit()
            return 1

        catalog_core.build_crosswalk_pad = fake_pad
        try:
            with tempfile.TemporaryDirectory() as directory:
                catalog = Catalog(init_catalog_db(os.path.join(directory, "catalog.db")))
                stats = catalog.import_pad_addresses(["10005"])
                self.assertEqual(stats["pad_crosswalk_rows_added"], 1)
                self.assertEqual(stats["pad_addresses_in_scope"], 1)
                self.assertEqual(catalog.conn.execute("SELECT COUNT(*) FROM addresses").fetchone()[0], 1)
                self.assertEqual(catalog.conn.execute("SELECT COUNT(*) FROM units").fetchone()[0], 0)
        finally:
            catalog_core.build_crosswalk_pad = original

    def test_reports_active_listing_resolution_by_source_and_zip(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Catalog(init_catalog_db(os.path.join(directory, "catalog.db")))
            listings_path = os.path.join(directory, "listings.db")
            listings = __import__("sqlite3").connect(listings_path)
            listings.execute(
                "CREATE TABLE listings (source TEXT, source_id TEXT, zipcode TEXT, status TEXT)"
            )
            listings.executemany(
                "INSERT INTO listings VALUES (?,?,?,?)",
                [("feed", "a", "10005", "active"), ("feed", "b", "10005", "active"),
                 ("feed", "c", "10006", "inactive")],
            )
            listings.commit()
            listings.close()
            catalog.conn.execute(
                "INSERT INTO observations (observation_id,source,source_ref,observed_at,"
                "observation_kind,evidence_grade) VALUES ('obs_a','feed','a','2026-07-01','listing','source_document')"
            )
            catalog.conn.execute(
                "INSERT INTO entity_matches VALUES ('obs_a','unit','unit_a','resolved',1,'test','test','2026-07-01')"
            )
            catalog.conn.commit()
            self.assertEqual(catalog.listing_zipcodes(listings_path), ["10005"])
            self.assertEqual(catalog.listing_coverage(listings_path), [{
                "source": "feed", "zipcode": "10005", "listings": 2, "resolved": 1,
                "unresolved": 1, "resolution_rate": 0.5,
            }])

    def test_preserves_multiple_official_bbl_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Catalog(init_catalog_db(os.path.join(directory, "catalog.db")))
            for bbl in ("1000000001", "1000000002"):
                catalog.conn.execute(
                    "INSERT INTO addresses VALUES (?,?,?,?,?,?)",
                    (f"addr_{bbl}", bbl, "10 West Street", "10 W ST", "10001", "test"),
                )
            catalog.conn.commit()
            catalog._record_bbl_candidates("observation", "10 West Street", "10001")
            candidates = catalog.conn.execute(
                "SELECT candidate_id FROM entity_match_candidates ORDER BY candidate_id"
            ).fetchall()
            self.assertEqual(candidates, [("1000000001",), ("1000000002",)])

    def test_resolves_ambiguous_listing_with_unique_official_unit_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Catalog(init_catalog_db(os.path.join(directory, "catalog.db")))
            catalog._source("hpd_violations", "public_record", "test")
            catalog._source("broker", "listing_feed", "test")
            catalog.conn.execute(
                "INSERT INTO units VALUES ('unit_1','1000000001','7A','7A','2026-01-01','2026-01-01')"
            )
            catalog.conn.execute(
                "INSERT INTO observations (observation_id,source,source_ref,observed_at,observation_kind,address,unit_label,evidence_grade) "
                "VALUES ('official','hpd_violations','v1','2026-01-01','official_unit_mention','10 West Street','7A','source_document')"
            )
            catalog._match("official", "unit", "unit_1", "resolved", 1.0,
                           "official_bbl_and_unit_label", "test")
            catalog.conn.execute(
                "INSERT INTO observations (observation_id,source,source_ref,observed_at,observation_kind,address,unit_label,evidence_grade) "
                "VALUES ('listing','broker','l1','2026-01-01','listing','10 West Street','7A','source_document')"
            )
            catalog._match("listing", "building", None, "ambiguous", 0.0, "test", "test")
            catalog._match("listing", "unit", None, "ambiguous", 0.0, "test", "test")
            catalog.conn.executemany(
                "INSERT INTO entity_match_candidates VALUES (?,?,?,?,?)",
                [("listing", "building", "1000000001", "test", "test"),
                 ("listing", "building", "1000000002", "test", "test")],
            )
            catalog.conn.commit()
            stats = catalog.reconcile_unit_candidates()
            self.assertEqual(stats["candidate_units_resolved"], 1)
            unit_match = catalog.conn.execute(
                "SELECT entity_id, status, method FROM entity_matches WHERE observation_id='listing' AND entity_type='unit'"
            ).fetchone()
            self.assertEqual(unit_match, ("unit_1", "resolved", "unique_official_unit_corroboration"))
            evidence_links = catalog.conn.execute(
                "SELECT entity_type, evidence_observation_id FROM entity_match_evidence "
                "WHERE observation_id='listing' ORDER BY entity_type"
            ).fetchall()
            self.assertEqual(evidence_links, [("building", "official"), ("unit", "official")])

    def test_keeps_candidate_ambiguous_when_official_address_differs(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Catalog(init_catalog_db(os.path.join(directory, "catalog.db")))
            catalog._source("hpd_violations", "public_record", "test")
            catalog._source("broker", "listing_feed", "test")
            catalog.conn.execute(
                "INSERT INTO units VALUES ('unit_1','1000000001','7A','7A','2026-01-01','2026-01-01')"
            )
            catalog.conn.execute(
                "INSERT INTO observations (observation_id,source,source_ref,observed_at,observation_kind,address,unit_label,evidence_grade) "
                "VALUES ('official','hpd_violations','v1','2026-01-01','official_unit_mention','12 West Street','7A','source_document')"
            )
            catalog._match("official", "unit", "unit_1", "resolved", 1.0,
                           "official_bbl_and_unit_label", "test")
            catalog.conn.execute(
                "INSERT INTO observations (observation_id,source,source_ref,observed_at,observation_kind,address,unit_label,evidence_grade) "
                "VALUES ('listing','broker','l1','2026-01-01','listing','10 West Street','7A','source_document')"
            )
            catalog._match("listing", "building", None, "ambiguous", 0.0, "test", "test")
            catalog._match("listing", "unit", None, "ambiguous", 0.0, "test", "test")
            catalog.conn.executemany(
                "INSERT INTO entity_match_candidates VALUES (?,?,?,?,?)",
                [("listing", "building", "1000000001", "test", "test"),
                 ("listing", "building", "1000000002", "test", "test")],
            )
            catalog.conn.commit()
            stats = catalog.reconcile_unit_candidates()
            self.assertEqual(stats["candidate_units_resolved"], 0)
            self.assertEqual(stats["candidate_units_still_ambiguous"], 1)


if __name__ == "__main__":
    unittest.main()
