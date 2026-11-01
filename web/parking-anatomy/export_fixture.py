"""Export bookings and real Qiskit circuits for each supported waiting weight."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import qiskit
from main import sample_scenario
from src.ev_scheduler import generate_options, solve_exact
from src.quantum_scheduler import build_qubo, qubo_to_ising, build_qaoa_circuit, qubo_value

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
print(json.dumps({'scenario': scenario,
                  'options': [o for group in generated['options'].values() for o in group],
                  'rejected': generated['rejected'],
                  'baseline': solve_exact(scenario, generated['options']),
                  'quantum': {'qiskit_version': qiskit.__version__, 'qubits': 5, 'layers': 2,
                              'bit_order': 'q0 q1 q2 q3 q4', 'records': records}}, separators=(',', ':')))
