import copy
import json
import unittest
from pathlib import Path
from robot_reel.compare import compatible, verify_comparison
from robot_reel.microduck import validate_speed

ROOT = Path(__file__).resolve().parents[1]/'docs/compare'

class ComparisonTest(unittest.TestCase):
    def test_published_bundles_verify(self):
        for name in ('microduck', 'braking'):
            with self.subTest(name=name):
                self.assertEqual(verify_comparison(ROOT/name)['family'], name)

    def test_incompatible_trials_are_rejected(self):
        a = json.loads((ROOT/'braking/left-trace.json').read_text())
        b = json.loads((ROOT/'braking/right-trace.json').read_text())
        self.assertEqual(compatible(a,b), 'braking')
        for mutate in (lambda t: t['frames'].pop(),
                       lambda t: t['frames'][0].update(sim_time=.9),
                       lambda t: t['config'].update(initial_speed_mps=999),
                       lambda t: t.update(units=['wrong'])):
            changed=copy.deepcopy(b); mutate(changed)
            with self.assertRaises(ValueError): compatible(a,changed)

    def test_policy_identity_must_match(self):
        a=json.loads((ROOT/'microduck/left-trace.json').read_text())
        b=copy.deepcopy(a); b['policy']['sha256']='different'
        with self.assertRaisesRegex(ValueError,'sha256'): compatible(a,b)

    def test_speed_rejects_invalid_values(self):
        for value in (-.1,.7,float('nan'),float('inf'),True,'0.3'):
            with self.subTest(value=value), self.assertRaises(ValueError): validate_speed(value)
        for value in (0,.3,.6): validate_speed(value)
