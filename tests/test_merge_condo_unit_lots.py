import sqlite3
import unittest

from tools.merges.merge_condo_unit_lots import target_rows


class CondoUnitLotTargetTests(unittest.TestCase):
    def test_prior_direct_observation_is_not_replayed(self):
        catalog = sqlite3.connect(":memory:")
        catalog.executescript(
            """
            create table official_unit_lots (
                unit_lot_bbl text, unit_designation text, source_ref text,
                document_id text, condo_base_bbl text
            );
            create table units (bbl text);
            create table observations (
                source text, source_ref text, observation_kind text
            );
            insert into official_unit_lots values
                ('1000000001','1A','new-ref','doc-new','1000000000'),
                ('1000000002','1B','old-ref','doc-old','1000000000'),
                ('1000000003','1C','named-ref','doc-named','1000000000');
            insert into units values ('1000000003');
            insert into observations values
                ('dof_condo_unit_lots_direct','old-ref','dof_condo_unit_lot_registration');
            """
        )
        all_targets, new_targets = target_rows(catalog)
        self.assertEqual(len(all_targets), 2)
        self.assertEqual([row[0] for row in new_targets], ['1000000001'])


if __name__ == "__main__":
    unittest.main()
