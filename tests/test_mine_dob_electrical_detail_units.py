import unittest
from unittest.mock import patch

from tools.merges.mine_dob_electrical_detail_units import (
    extract_electrical_detail_labels,
    normalize_bbl,
    observed_date,
    query_details,
)


class DobElectricalDetailTest(unittest.TestCase):
    def test_normalizes_parent_identity_fields(self):
        self.assertEqual(normalize_bbl("1004060059"), "1004060059")
        self.assertEqual(normalize_bbl("bad"), "")
        self.assertEqual(observed_date("2018-04-18T00:00:00.000"), "2018-04-18")

    def test_extracts_source_specific_explicit_labels(self):
        self.assertEqual(
            extract_electrical_detail_labels("Apts. 1b, 2b, 4b and 5b"),
            ["1B", "2B", "4B", "5B"],
        )
        self.assertEqual(extract_electrical_detail_labels("Apartment Unit #10J"), ["10J"])
        self.assertEqual(extract_electrical_detail_labels("16th Floor, Apartment G"), ["G"])
        self.assertEqual(
            extract_electrical_detail_labels("3L,3R rewire apartments"), ["3L", "3R"]
        )
        self.assertEqual(
            extract_electrical_detail_labels("work in apartments 1A1B1C1D2A"),
            ["1A", "1B", "1C", "1D", "2A"],
        )
        self.assertEqual(
            extract_electrical_detail_labels("Apartment 6A 6B 6C 6D"),
            ["6A", "6B", "6C", "6D"],
        )
        self.assertEqual(extract_electrical_detail_labels("Apt A and B"), ["A", "B"])
        self.assertEqual(extract_electrical_detail_labels("Apartment 12 C"), ["12C"])
        self.assertEqual(extract_electrical_detail_labels("Apartment 417 517"), ["417", "517"])
        self.assertEqual(extract_electrical_detail_labels("Apt 31 CD"), ["31CD"])
        self.assertEqual(extract_electrical_detail_labels("General Wiring in Unit 27"), ["27"])
        self.assertEqual(extract_electrical_detail_labels("Unit TH"), ["TH"])

    def test_rejects_generic_equipment_units(self):
        self.assertEqual(extract_electrical_detail_labels("HVAC units and generator"), [])
        self.assertEqual(extract_electrical_detail_labels("Compressor Unit only"), [])
        self.assertEqual(extract_electrical_detail_labels("A/C UNIT ON THE ROOF"), [])
        self.assertEqual(extract_electrical_detail_labels("split unit AC on first floor"), [])
        self.assertEqual(extract_electrical_detail_labels("4 INDOOR UNITS"), [])
        self.assertEqual(extract_electrical_detail_labels("38 apts on these floors"), [])
        self.assertEqual(
            extract_electrical_detail_labels(
                "SUMMONS NUMBER 039019280R IN APT. 12G - REPLACE LIGHTS"
            ),
            ["12G"],
        )
        self.assertEqual(extract_electrical_detail_labels("Apartment 508General Wiring"), [])
        self.assertEqual(
            extract_electrical_detail_labels("APARTMENT 1F, 220V ELECTRICAL STOVE"), ["1F"]
        )

    @patch("tools.merges.mine_dob_electrical_detail_units.urlopen")
    def test_detail_query_is_bounded_to_apartment_markers(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = b"[]"
        self.assertEqual(query_details(0, 100), [])
        url = urlopen.call_args.args[0].full_url
        self.assertIn("floor_detail", url)
        self.assertIn("unique_id%2Cjob_filing_number", url)


if __name__ == "__main__":
    unittest.main()
