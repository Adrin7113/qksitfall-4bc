import sys
import os
from pathlib import Path
sys.path.insert(0,os.environ.get('PARKING_SOURCE_ROOT',str(Path(__file__).resolve().parents[2])))
import numpy as np
import ast, json, operator
from qiskit import QuantumCircuit
fixture=json.loads((Path(__file__).parent/"fixture.json").read_text())
def angle(text,beta,gamma):
 for name,values in (("beta",beta),("gamma",gamma)):
  for i,v in enumerate(values):text=text.replace(f"{name}[{i}]",repr(float(v)))
 def walk(n):
  if isinstance(n,ast.Constant):return n.value
  if isinstance(n,ast.UnaryOp) and isinstance(n.op,ast.USub):return -walk(n.operand)
  if isinstance(n,ast.BinOp):return {ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv}[type(n.op)](walk(n.left),walk(n.right))
  raise ValueError("Unexpected angle expression")
 return walk(ast.parse(text,mode="eval").body)
from qiskit.quantum_info import Statevector
from main import sample_scenario
from src.ev_scheduler import generate_options
from src.quantum_scheduler import build_qubo,qubo_to_ising,build_qaoa_circuit,qubo_value
rng=np.random.default_rng(41);worst=0
for tick in range(101):
 s=sample_scenario();s['waiting_weight_per_minute']=tick/100
 m=build_qubo(s,generate_options(s)['options']);h=qubo_to_ising(m);q=build_qaoa_circuit(h,2)
 energies=np.array([qubo_value(m,[(i>>j)&1 for j in range(5)]) for i in range(32)])
 for trial in range(3):
  beta=rng.uniform(-2,2,2);gamma=rng.uniform(-2,2,2)
  expected=np.ones(32,dtype=complex)/np.sqrt(32)
  for b,g in zip(beta,gamma):
   expected*=np.exp(-1j*g*(energies-h['offset'])/h['scale'])
   single=np.array([[np.cos(b),-1j*np.sin(b)],[-1j*np.sin(b),np.cos(b)]])
   mix=single
   for _ in range(4):mix=np.kron(mix,single)
   expected=mix@expected
  binding={p:(beta if p.name.startswith('beta') else gamma)[p.index] for p in q.parameters}
  actual=Statevector.from_instruction(q.assign_parameters(binding)).data
  exported=QuantumCircuit(5)
  for op in fixture['quantum']['records'][tick]['operations']:
   name=op['name']
   if name in ('measure','barrier'):continue
   if name=='h':exported.h(op['qubits'][0])
   else:getattr(exported,name)(angle(op['parameters'][0],beta,gamma),*op['qubits'])
  exported_state=Statevector.from_instruction(exported).data
  assert np.max(np.abs(exported_state-expected))<1e-10,('export mismatch',tick,trial)
  error=float(np.max(np.abs(expected-actual)));worst=max(worst,error)
  assert error<1e-10,(tick,trial,error)
print('PASS: 303 independent two-layer statevector comparisons, including exported browser gate data; worst amplitude error',worst)

# Check the new eight-qubit circuit against an independent diagonal cost and
# tensor-product mixer, including the exact gate records sent to the browser.
from shared_power_demo import sample_shared_power_scenario
from src.shared_power_scheduler import build_shared_power_qubo
m=build_shared_power_qubo(sample_shared_power_scenario())
h=qubo_to_ising(m);q=build_qaoa_circuit(h,2)
energies=np.array([qubo_value(m,[(i>>j)&1 for j in range(8)]) for i in range(256)])
worst_shared=0
for trial in range(3):
 beta=rng.uniform(-2,2,2);gamma=rng.uniform(-2,2,2)
 expected=np.ones(256,dtype=complex)/16
 for b,g in zip(beta,gamma):
  expected*=np.exp(-1j*g*(energies-h['offset'])/h['scale'])
  single=np.array([[np.cos(b),-1j*np.sin(b)],[-1j*np.sin(b),np.cos(b)]])
  mix=single
  for _ in range(7):mix=np.kron(mix,single)
  expected=mix@expected
 binding={p:(beta if p.name.startswith('beta') else gamma)[p.index] for p in q.parameters}
 actual=Statevector.from_instruction(q.assign_parameters(binding)).data
 exported=QuantumCircuit(8)
 for op in fixture['shared_power']['quantum']['operations']:
  if op['name'] in ('measure','barrier'):continue
  if op['name']=='h':exported.h(op['qubits'][0])
  else:getattr(exported,op['name'])(angle(op['parameters'][0],beta,gamma),*op['qubits'])
 export_error=float(np.max(np.abs(Statevector.from_instruction(exported).data-expected)))
 actual_error=float(np.max(np.abs(actual-expected)))
 worst_shared=max(worst_shared,export_error,actual_error)
 assert max(export_error,actual_error)<1e-10,('shared-power circuit mismatch',trial,export_error,actual_error)
print('PASS: 3 independent eight-qubit statevector and browser export comparisons; worst amplitude error',worst_shared)
