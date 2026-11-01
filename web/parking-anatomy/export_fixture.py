"""Export bookings and real Qiskit circuits for each supported waiting weight."""
import json
import os
import sys
from hashlib import sha256
from pathlib import Path

source_root = Path(os.environ.get('PARKING_SOURCE_ROOT', Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(source_root))
import qiskit
from main import sample_scenario
from src.ev_scheduler import generate_options, solve_exact
from src.quantum_scheduler import build_qubo, qubo_to_ising, build_qaoa_circuit, qubo_value
from src.quantum_scheduler import solve_qaoa
from src.shared_power_scheduler import build_shared_power_qubo, decode_shared_power_bits, solve_shared_power_exact
from shared_power_demo import sample_shared_power_scenario

from src.quantum_benchmark import validate_report
benchmark = json.loads((Path(__file__).resolve().parent / 'benchmark.json').read_text())
validate_report(benchmark, source_root)

scenario = sample_scenario()
generated = generate_options(scenario)
records = []
for tick in range(101):
    current = sample_scenario()
    current['waiting_weight_per_minute'] = tick / 100
    options = generate_options(current)['options']
    model = build_qubo(current, options)
    ising = qubo_to_ising(model)
    circuit = build_qaoa_circuit(ising, layers=2)
    circuit.measure_all()
    operations = []
    for instruction in circuit.data:
        operation = instruction.operation
        operations.append({'name': operation.name,
                           'qubits': [circuit.find_bit(q).index for q in instruction.qubits],
                           'clbits': [circuit.find_bit(c).index for c in instruction.clbits],
                           'parameters': [str(p) for p in operation.params]})
    records.append({'weight': tick / 100, 'penalty': model['penalty'],
                    'score_bound': model['score_bound'], 'z': ising['z'],
                    'zz': [[i, j, v] for (i, j), v in ising['zz'].items()],
                    'scale': ising['scale'], 'offset': ising['offset'],
                    'operations': operations,
                    'energies': [qubo_value(model, [int(x) for x in f'{i:05b}']) for i in range(32)],
                    'gate_counts': dict(circuit.count_ops()),
                    'parameter_order': [str(p) for p in circuit.parameters]})
shared = build_shared_power_qubo(sample_shared_power_scenario())
shared_ising = qubo_to_ising(shared)
shared_circuit = build_qaoa_circuit(shared_ising, layers=2)
shared_circuit.measure_all()
shared_operations = [
    {'name': instruction.operation.name,
     'qubits': [shared_circuit.find_bit(q).index for q in instruction.qubits],
     'clbits': [shared_circuit.find_bit(c).index for c in instruction.clbits],
     'parameters': [str(p) for p in instruction.operation.params]}
    for instruction in shared_circuit.data
]
shared_reference = solve_shared_power_exact(shared)
shared_states = []
for value in range(2 ** len(shared['variables'])):
    bits = [int(x) for x in f'{value:08b}']
    decoded = decode_shared_power_bits(shared, bits)
    objective = sum(p['score'] * bit for p, bit in zip(shared['variables'], bits))
    energy = qubo_value(shared, bits)
    shared_states.append({'bits': ''.join(map(str, bits)), 'valid': decoded['valid'],
                          'reasons': decoded['reasons'], 'objective': objective,
                          'energy': energy, 'penalty': energy - objective})
shared_run = solve_qaoa(shared, layers=2, iterations=80, restarts=2, shots=2048, seed=7)
def shared_bits(*choices):
    return ''.join(str(int((p['vehicle_id'], p['gun'], p['power_kw_by_slot']) in choices))
                   for p in shared['variables'])
shared_fixture = {
    'scenario': shared['scenario'], 'plans': shared['variables'], 'groups': shared['groups'],
    'penalty': shared['penalty'], 'score_bound': shared['score_bound'],
    'constant': shared['constant'], 'linear': shared['linear'],
    'quadratic': [[i, j, value] for (i, j), value in shared['quadratic'].items()],
    'conflicts': shared['conflicts'], 'reference': shared_reference, 'states': shared_states,
    'presets': {'optimal': ''.join(map(str, shared_reference['bits'])),
                'delayed': shared_bits(('A', 0, (50, 25)), ('B', 1, (0, 25))),
                'overload': shared_bits(('A', 0, (50, 25)), ('B', 1, (25, 0))),
                'gun': shared_bits(('A', 0, (25, 50)), ('B', 0, (25, 0)))},
    'quantum': {'num_qubits': 8, 'layers': 2, 'operations': shared_operations,
                'z': shared_ising['z'], 'zz': [[i, j, v] for (i, j), v in shared_ising['zz'].items()],
                'scale': shared_ising['scale'], 'offset': shared_ising['offset'],
                'gate_counts': dict(shared_circuit.count_ops()),
                'parameter_order': [str(p) for p in shared_circuit.parameters]},
    'saved_run': {key: shared_run[key] for key in ('status', 'bits', 'shots', 'seed', 'layers',
                  'valid_shots', 'valid_sample_fraction', 'total_flow_minutes', 'average_flow_minutes')},
}
shared_fixture['saved_run'].update(iterations=80, restarts=2, backend='local Qiskit Aer statevector')
print(json.dumps({'scenario': scenario,
                  'options': [o for group in generated['options'].values() for o in group],
                  'rejected': generated['rejected'],
                  'baseline': solve_exact(scenario, generated['options']),
                  'quantum': {'qiskit_version': qiskit.__version__, 'qubits': 5, 'layers': 2,
                              'bit_order': 'q0 q1 q2 q3 q4', 'records': records},
                  'shared_power': shared_fixture,
                  'benchmark': benchmark,
                  'source_hashes': {name: sha256((source_root / name).read_bytes()).hexdigest()
                                    for name in ('src/ev_scheduler.py', 'src/quantum_scheduler.py',
                                                 'src/shared_power_scheduler.py', 'shared_power_demo.py',
                                                 'src/quantum_benchmark.py', 'scripts/benchmark_quantum.py')}},
                 separators=(',', ':')))
