import unittest

from pricefixed.engine.unit_mentions import extract_explicit_unit_labels


class ExplicitUnitMentionTest(unittest.TestCase):
    def test_extracts_single_and_separated_lists(self):
        self.assertEqual(extract_explicit_unit_labels("WORK IN APT 6C"), ["6C"])
        self.assertEqual(extract_explicit_unit_labels("Apts 1R and 1F, 2R. 2F"), ["1R", "1F", "2R", "2F"])

    def test_expands_clear_compounds_and_shorthand(self):
        self.assertEqual(extract_explicit_unit_labels("APARTMENT 14J/14K"), ["14J", "14K"])
        self.assertEqual(extract_explicit_unit_labels("APARTMENT 12B/C"), ["12B", "12C"])
        self.assertEqual(
            extract_explicit_unit_labels("APARTMENTS B701-B702-B703"),
            ["B701", "B702", "B703"],
        )
        self.assertEqual(extract_explicit_unit_labels("APARTMENT 26 C&D"), ["26C", "26D"])
        self.assertEqual(
            extract_explicit_unit_labels("APARTMENT 12 C,D,E"),
            ["12C", "12D", "12E"],
        )
        self.assertEqual(extract_explicit_unit_labels("DWELLING UNIT 13 D+E"), ["13D", "13E"])
        self.assertEqual(
            extract_explicit_unit_labels("APARTMENT 12 D E F WITH MINOR WORK"),
            ["12D", "12E", "12F"],
        )
        self.assertEqual(extract_explicit_unit_labels("WORK AT APT'S 4NC"), ["4NC"])
        self.assertEqual(
            extract_explicit_unit_labels("WORK AT APT'S 4NC AND 4ND"),
            ["4NC", "4ND"],
        )
        self.assertEqual(extract_explicit_unit_labels("APTS 2RR AND 2"), ["2RR", "2"])

    def test_rejects_ambiguous_compound_and_ignores_plain_words(self):
        self.assertEqual(extract_explicit_unit_labels("Renovation of Apartment 2/3D"), [])
        self.assertEqual(extract_explicit_unit_labels("CHAPTER 33 APPLIES"), [])
        self.assertEqual(extract_explicit_unit_labels("Apartment 117689"), [])

    def test_joins_space_separated_suffix(self):
        self.assertEqual(extract_explicit_unit_labels("plumbing work in apt 2 R only"), ["2R"])
        self.assertEqual(extract_explicit_unit_labels("electrical work in apartment 12 C"), ["12C"])

    def test_does_not_take_prose_or_floor_ordinals_as_suffixes(self):
        self.assertEqual(extract_explicit_unit_labels("renovation of apt 8 as per plans"), ["8"])
        self.assertEqual(extract_explicit_unit_labels("work to apt 1R, 1st floor"), ["1R"])
        self.assertEqual(extract_explicit_unit_labels("apartment 3 including a bath"), ["3"])
        self.assertEqual(extract_explicit_unit_labels("APT #2FLINCLUDING WORK"), [])
        self.assertEqual(extract_explicit_unit_labels("apartment 2nd floor"), [])
        self.assertEqual(extract_explicit_unit_labels("apt 1stfl, 1st story"), [])
        self.assertEqual(extract_explicit_unit_labels("Apartment 4ND."), [])

    def test_splits_prose_concatenated_to_a_label(self):
        self.assertEqual(extract_explicit_unit_labels("APT 8DEXISTING"), ["8D"])
        self.assertEqual(extract_explicit_unit_labels("APT 6AINSTALL"), ["6A"])
        self.assertEqual(extract_explicit_unit_labels("APT16CPROPOSED"), ["16C"])
        self.assertEqual(extract_explicit_unit_labels("APT#2D,2E,2G,3HAND"), ["2D", "2E", "2G", "3H"])
        self.assertEqual(extract_explicit_unit_labels("APT 12Dand 12E"), ["12D", "12E"])
        self.assertEqual(extract_explicit_unit_labels("APT 5ANO CHANGE OF USE"), ["5A"])
        self.assertEqual(extract_explicit_unit_labels("APT 8NO AND 8F"), ["8NO", "8F"])

    def test_expands_compact_thru_ranges_with_matching_suffixes(self):
        self.assertEqual(
            extract_explicit_unit_labels("APT. 2ATHRU5A"),
            ["2A", "3A", "4A", "5A"],
        )
        self.assertEqual(extract_explicit_unit_labels("APT. 2ATHRU5B"), [])

    def test_normalizes_single_hyphenated_suffix(self):
        self.assertEqual(extract_explicit_unit_labels("apartments 7-D and 7-E"), ["7D", "7E"])


if __name__ == "__main__":
    unittest.main()
