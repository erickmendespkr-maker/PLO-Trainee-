import csv
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import closing

import strategic_normalize as n
import strategic_store as s
import strategic_import as imp
import strategic_backup as backup


def scenario(**changes):
    data = dict(schema=n.SCHEMA, players=6, position='BTN', street='flop',
                hero=['As','Kd','Qh','Jc','Ts'], board=['2s','3d','4h'],
                amount_unit='BB', bb_size=1, stack=100, pot=20, to_call=5,
                rake_percent=5, rake_cap=3, frequency_unit='fraction',
                ev_baseline='decision', model='fixture model', node='fixture node')
    data.update(changes)
    return data


def actions():
    return [dict(action='fold', size=0, frequency=.25, ev=0),
            dict(action='call', size=5, frequency=.75, ev=-1.5)]


class NormalizeTests(unittest.TestCase):
    def test_canonical_cards_and_positions(self):
        raw = scenario(hero=['10S','jC','QH','kd',' aS '], position=' btn ', street='FLOP', board=['4h','2s','3d'])
        self.assertEqual(n.normalize_scenario(5, raw), n.normalize_scenario(5, scenario()))

    def test_six_cards_and_street_order(self):
        raw = scenario(street='river', hero=scenario()['hero']+['9s'], board=['4h','2s','3d','5c','6c'])
        canonical = n.normalize_scenario(6, raw)
        self.assertEqual(canonical['board'], ['2s','3d','4h','5c','6c'])
        self.assertNotEqual(canonical, n.normalize_scenario(6, dict(raw, board=raw['board'][:3]+['6c','5c'])))

    def test_duplicate_and_invalid_cards(self):
        for raw in (scenario(hero=['As']*5), scenario(board=['As','2s','3d']),
                    scenario(board=['2x','3d','4h']), scenario(street='turn'), scenario(hero=['As'])):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                n.normalize_scenario(5, raw)

    def test_table_and_variant(self):
        for raw in (scenario(players=2), scenario(players=7), scenario(position='EP'), scenario(players=True)):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                n.normalize_scenario(5, raw)
        with self.assertRaises(ValueError):
            n.normalize_scenario(5.0, scenario())
        self.assertEqual(n.normalize_scenario(5, scenario(players=2, position='SB'))['players'], 2)

    def test_unit_equivalence_and_negative_ev(self):
        raw = scenario(amount_unit='chips', bb_size=2, stack=200, pot=40, to_call=10, rake_cap=6, frequency_unit='percent')
        aa = [dict(a, size=a['size']*2, frequency=a['frequency']*100, ev=a['ev']*2) for a in actions()]
        pair = n.normalize_record(5, raw, aa)
        self.assertEqual(pair, n.normalize_record(5, scenario(), actions()))
        self.assertEqual(pair[1][0]['ev'], '-1.5')
        self.assertEqual(pair, n.normalize_record(5, *pair))

    def test_bad_units_and_values(self):
        for raw in (scenario(bb_size=0), scenario(amount_unit='USD'), scenario(pot=float('nan')),
                    scenario(to_call=101), scenario(rake_percent=101), scenario(ev_baseline='unknown'),
                    scenario(frequency_unit='auto'), scenario(stack=True), scenario(model=''), scenario(to_call='1e-12'),
                    scenario(amount_unit='chips', bb_size='1e-999999')):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                n.normalize_scenario(5, raw)

    def test_action_bounds(self):
        for a in (dict(action='raise',size=31,frequency=1,ev=0), dict(action='check',size=0,frequency=1,ev=0),
                  dict(action='call',size=4,frequency=1,ev=0), dict(action='fold',size=0,frequency=2,ev=0),
                  dict(action='fold',size=0,frequency=.5,ev=0), dict(action='fold',size=0,frequency=1,ev=float('inf'))):
            with self.subTest(a=a), self.assertRaises(ValueError):
                n.normalize_record(5, scenario(), [a])
        self.assertEqual(n.normalize_record(5, scenario(), [dict(action='raise',size=30,frequency=1,ev=None)])[1][0]['size'], '30')

    def test_duplicate_sizing_and_multiple_sizes(self):
        a = dict(action='raise',size=20,frequency=.5,ev=None)
        with self.assertRaises(ValueError):
            n.normalize_record(5, scenario(), [a,a])
        self.assertEqual(len(n.normalize_record(5, scenario(), [a,dict(a,size=30)])[1]), 2)

    def test_node_distinction(self):
        self.assertNotEqual(s.scenario_identity(5, scenario()), s.scenario_identity(5, scenario(node='different')))

    def test_db_import_lookup_backup(self):
        with tempfile.TemporaryDirectory() as folder, closing(s.connect(Path(folder)/'s.db')) as db:
            source = s.add_source(db, 'fixture', 'test only', 'local')
            for suffix in ('json','csv','txt'):
                path = Path(folder)/('rows.'+suffix)
                if suffix == 'json':
                    path.write_text(json.dumps(dict(format=imp.FORMAT_V2, records=[dict(variant=5,scenario=scenario(),actions=actions())])))
                else:
                    with path.open('w',newline='') as handle:
                        writer = csv.writer(handle,delimiter=',' if suffix=='csv' else '\t')
                        writer.writerow(imp.FIELDS)
                        writer.writerow([5,json.dumps(scenario()),json.dumps(actions())])
                report = imp.import_fixture(db,path,source_id=source,synthetic=True)
                self.assertEqual(report['inserted'], int(suffix=='json'))
            self.assertEqual(s.lookup(db,5,scenario(),synthetic=True), [(source,n.normalize_record(5,scenario(),actions())[1])])
            self.assertEqual(s.lookup(db,5,scenario()), [])
            self.assertEqual(backup.backup(Path(folder)/'s.db',Path(folder)/'copy.db')['counts']['records'],1)

    def test_version_mismatch(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'rows.json'
            path.write_text(json.dumps(dict(format=imp.FORMAT, records=[dict(variant=5,scenario=scenario(),actions=actions())])))
            with self.assertRaisesRegex(ValueError,'version'):
                imp.read_file(path,source_id='fixture')

    def test_real_write_still_blocked(self):
        with self.assertRaises(ValueError):
            s.prepare_record('fixture',5,scenario(),actions(),synthetic=False)


if __name__ == '__main__':
    unittest.main()
