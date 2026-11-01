import json
import tempfile
import importlib.util
from pathlib import Path
from copy import deepcopy
import random
import unittest
from classical_and_scaling import solve_booking_assignment,solve_fairness_totals,fairness_encoding,statevector_bytes,shots_for_hit

HERE=Path(__file__).resolve().parent

def embedded_module(marker,name,directory):
    notebook=json.loads((HERE/'ev-scheduling-validation.ipynb').read_text())
    cell=next(c for c in notebook['cells'] if c['cell_type']=='code' and ''.join(c['source']).startswith('%%writefile '+marker))
    source=''.join(cell['source']).split('\n',1)[1]
    path=directory/(name+'.py');path.write_text(source)
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

class BaselinesAndProjections(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace=tempfile.TemporaryDirectory();root=Path(cls.workspace.name)
        cls.booking=embedded_module('$BOOKING_PATH','booking_test_reference',root)
        cls.fairness=embedded_module('$FAIRNESS_PATH','fairness_test_reference',root)
    @classmethod
    def tearDownClass(cls):cls.workspace.cleanup()

    def test_assignment_matches_all_101_weights(self):
        for w in range(101):
            model=self.booking.build_model({'waiting_weight':w/100})
            result=solve_booking_assignment(model['metadata']['options'],['A','B'],w/100)
            self.assertAlmostEqual(result['score'],model['metadata']['exact_optimum'])
        self.assertIsNone(solve_booking_assignment([],['A','B']))

    def test_assignment_handles_random_graphs_and_bottlenecks(self):
        from itertools import product
        rng=random.Random(41)
        for _ in range(60):
            vehicles=['A','B','C'];resources=[('S',str(i)) for i in range(4)]
            options=[{'vehicle_id':v,'station_id':s,'slot_id':t,'electricity_cost_rupees':rng.randint(0,20),
                      'waiting_minutes':rng.randint(0,20)} for v in vehicles for s,t in resources if rng.random()<.6]
            groups=[[i for i,o in enumerate(options) if o['vehicle_id']==v] for v in vehicles]
            scores=[]
            for indices in product(*groups):
                selected=[options[i] for i in indices]
                if len({(o['station_id'],o['slot_id']) for o in selected})==3:
                    scores.append(sum(o['electricity_cost_rupees']+.25*o['waiting_minutes'] for o in selected))
            actual=solve_booking_assignment(options,vehicles)
            if scores:self.assertAlmostEqual(actual['score'],min(scores))
            else:self.assertIsNone(actual)
        bottleneck=[{'vehicle_id':v,'station_id':'S','slot_id':'0','electricity_cost_rupees':1,'waiting_minutes':0} for v in ['A','B']]
        # Give the matrix enough columns, while A/B still compete for only one.
        bottleneck.append({'vehicle_id':'C','station_id':'S','slot_id':'1','electricity_cost_rupees':1,'waiting_minutes':0})
        bottleneck.append({'vehicle_id':'C','station_id':'S','slot_id':'2','electricity_cost_rupees':1,'waiting_minutes':0})
        self.assertIsNone(solve_booking_assignment(bottleneck,['A','B','C']))

    def test_totals_match_100_independent_encoded_scenarios(self):
        rng=random.Random(20261101)
        cases=[deepcopy(self.fairness.DEFAULT)]
        for _ in range(99):
            cases.append({'cars':[{'capacity':rng.choice([40,50,60,80]),'soc':rng.choice([0,30,60,90,99,100]),
                'fast':rng.choice([True,False]),'present':rng.choice([True,False])} for _ in range(2)],'rate':8})
        for scenario in cases:
            result=solve_fairness_totals(scenario)
            model=self.fairness.build_model(scenario)
            expected=model['metadata']['best']
            self.assertEqual((result['minimum'],result['total']),(expected['minimum'],expected['total']))
            index=sum(self.fairness.PAIRS.index(tuple(p))<<(3*t) for t,p in enumerate(result['schedule']))
            self.assertTrue(self.fairness.decode(index,scenario)['feasible'])
        self.assertEqual(solve_fairness_totals(self.fairness.DEFAULT)['feasible_total_pairs'],30)

        self.assertEqual(solve_fairness_totals(self.fairness.DEFAULT)['objective_evaluations'],4)

    def test_aggregate_feasibility_suffices_for_other_horizons(self):
        for slots in range(1,7):
            for rate_a in (0,1,2):
                for rate_b in (0,1,2):
                    reachable={(0,0)}
                    for _ in range(slots):
                        reachable={(a+x,b+y) for a,b in reachable for x in range(rate_a+1) for y in range(rate_b+1) if x+y<=2}
                    expected={(a,b) for a in range(slots*rate_a+1) for b in range(slots*rate_b+1) if a+b<=2*slots}
                    self.assertEqual(reachable,expected)

    def test_memory_and_shot_accounting(self):
        self.assertEqual(statevector_bytes(12),65536)
        self.assertEqual(fairness_encoding(100,100,4)['logical_qubits'],52)
        self.assertEqual(fairness_encoding(1000,1000,96)['logical_qubits'],1824)
        for p in (1e-3,1e-6,1e-9,10/4096):
            shots=shots_for_hit(p)
            import math
            self.assertGreaterEqual(-math.expm1(shots*math.log1p(-p)),0.95)
            self.assertLess(-math.expm1((shots-1)*math.log1p(-p)),0.95)
        self.assertIsNone(shots_for_hit(0));self.assertEqual(shots_for_hit(1),1)
        for bad in (-1,1.1,float('nan')):
            with self.assertRaises(ValueError):shots_for_hit(bad)
        with self.assertRaises(ValueError):fairness_encoding(2,3,4)

if __name__=='__main__':
    result=unittest.main(exit=False)
    if not result.result.wasSuccessful():raise SystemExit(1)
    print('CLASSICAL_AND_SCALING_VERIFIED')
