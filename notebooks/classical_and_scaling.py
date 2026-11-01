"""Exact structured baselines and explicit resource-accounting scenarios.

These estimates are not quantum speedup, energy-saving or physical-QPU forecasts.
"""
from fractions import Fraction as F
from math import comb, ceil, log, log1p, isfinite


def solve_booking_assignment(options, vehicle_ids, waiting_weight=0.25):
    """Minimum-cost assignment after shared physical option preprocessing.

    One appointment consumes exactly one station/slot resource for one car.
    This does not cover overlapping multi-slot jobs or coupled station powers.
    """
    import numpy as np
    from scipy.optimize import linear_sum_assignment
    if not isfinite(waiting_weight) or waiting_weight < 0:
        raise ValueError('Use a finite, nonnegative waiting weight')
    if not vehicle_ids or len(set(vehicle_ids)) != len(vehicle_ids):
        raise ValueError('Use distinct vehicle IDs')
    resources=sorted({(o['station_id'],o['slot_id']) for o in options})
    if len(resources)<len(vehicle_ids):
        return None
    costs=np.full((len(vehicle_ids),len(resources)),np.inf)
    chosen={}
    for i,vehicle in enumerate(vehicle_ids):
        for k,option in enumerate(options):
            if option['vehicle_id']!=vehicle:
                continue
            j=resources.index((option['station_id'],option['slot_id']))
            value=float(option['electricity_cost_rupees'])+waiting_weight*option['waiting_minutes']
            if not isfinite(value) or value < 0:
                raise ValueError('Reference booking costs must be finite and nonnegative')
            if value<costs[i,j]:
                costs[i,j]=value;chosen[i,j]=k
    try:
        rows,cols=linear_sum_assignment(costs)
    except ValueError:
        return None
    indices=[chosen[int(i),int(j)] for i,j in zip(rows,cols)]
    return {'option_indices':indices,'schedule':[options[k] for k in indices],
            'score':float(costs[rows,cols].sum()),'method':'exact minimum-cost assignment',
            'scope':'from prevalidated single-resource appointments'}


def solve_fairness_totals(scenario, slots=4):
    """Exact O(T) two-car solver in energy totals, independent of the rank table.

    A 25kW x15min block is 6.25kWh. Fixed presence in all slots is essential.
    Per-car unit caps plus sum(u)<=2T are sufficient for these two cars.
    """
    if type(slots) is not int or slots<1:
        raise ValueError('slots must be a positive integer')
    if not isinstance(scenario,dict):raise ValueError('Expected a scenario object')
    price=scenario.get('rate',8)
    if type(price) not in (int,float) or not isfinite(price) or price<0:raise ValueError('Invalid reported electricity rate')
    cars=scenario.get('cars')
    if not isinstance(cars,list) or len(cars)!=2:
        raise ValueError('Exactly two cars are required')
    caps=[];rates=[]
    for car in cars:
        if any(type(car.get(key)) not in (int,float) or not isfinite(car[key]) for key in ('capacity','soc')):
            raise ValueError('Finite capacity and state of charge required')
        if car['capacity']<=0 or not 0<=car['soc']<=100:
            raise ValueError('Invalid capacity or state of charge')
        if type(car.get('present')) is not bool or type(car.get('fast')) is not bool:
            raise ValueError('Boolean presence/capability required')
        rate=(2 if car['fast'] else 1) if car['present'] else 0
        headroom=F(str(car['capacity']))*(100-F(str(car['soc'])))/100
        caps.append(min(slots*rate,int(headroom/F(25,4))))
        rates.append(rate)
    best=None;winner=None;checked=0;pairs=0
    for a in range(caps[0]+1):
        # For fixed a, increasing b cannot worsen the primary objective and
        # strictly improves the energy tie-break. Only the upper boundary matters.
        b=min(caps[1],2*slots-a)
        checked+=1;pairs+=b+1
        final=[F(str(c['soc']))+F(625*u)/F(str(c['capacity'])) for c,u in zip(cars,(a,b))]
        present=[v for c,v in zip(cars,final) if c['present']]
        score=(min(present) if present else F(0),a+b)
        if best is None or score>best:
            best=score;winner=(a,b,final)
    a,b,final=winner
    # Put a slower car first. If both are slow, one unit leaves one unit free
    # everywhere; a remaining fast car may consume any residual slot capacity.
    schedule=[[0,0] for _ in range(slots)]
    for i in sorted(range(2),key=lambda i:rates[i]):
        remaining=(a,b)[i]
        for pair in schedule:
            units=min(remaining,rates[i],2-sum(pair)//25)
            pair[i]=25*units;remaining-=units
        assert remaining==0, 'Aggregate conditions failed schedule reconstruction'
    energy=F(25,4)*(a+b)
    return {'units':[a,b],'schedule':schedule,'final':list(map(float,final)),
        'minimum':float(best[0]) if any(c['present'] for c in cars) else None,
        'total':float(energy),'cost':float(energy*F(str(scenario.get('rate',8)))),
        'objective_evaluations':checked,'feasible_total_pairs':pairs,'method':'exact two-car aggregate allocation'}


def statevector_bytes(qubits):
    if type(qubits) is not int or qubits<0:
        raise ValueError('qubits must be a nonnegative integer')
    return 16*(1<<qubits)  # one complex128 amplitude; workspace is additional


def fairness_encoding(cars,fast_cars,slots):
    """Hypothetical extension: N fixed-present cars/docks; same50kW budget.

    K choices/slot: idle, one25kW, one50kW-capable car, two distinct25kW cars.
    Binary encoding reserves unused codes. It is not a fleet implementation.
    """
    if any(type(x) is not int for x in (cars,fast_cars,slots)) or cars<1 or not 0<=fast_cars<=cars or slots<1:
        raise ValueError('Invalid hypothetical system dimensions')
    choices=1+cars+fast_cars+comb(cars,2)
    bits_per_slot=(choices-1).bit_length()
    qubits=slots*bits_per_slot
    return {'cars':cars,'fast_cars':fast_cars,'slots':slots,
        'choices_per_slot':choices,'bits_per_slot':bits_per_slot,'logical_qubits':qubits,
        'encoded_states':1<<qubits,'statevector_bytes':statevector_bytes(qubits),
        'float64_cost_table_bytes':8*(1<<qubits)}


def shots_for_hit(probability,confidence=0.95):
    if not isfinite(probability) or not 0<=probability<=1 or not 0<confidence<1:
        raise ValueError('Invalid success probability or confidence')
    if probability==0:return None
    if probability==1:return 1
    return ceil(log1p(-confidence)/log1p(-probability))


def projections():
    return {
      'scope':'accounting only; no measured or predicted quantum savings',
      'fairness_encoding':[fairness_encoding(*case) for case in [(2,2,4),(2,2,24),(100,100,4),(1000,1000,96)]],
      'booking_encoding':[{'cars':n,'stations':s,'slots':t,'maximum_option_qubits':n*s*t}
                          for n,s,t in [(2,2,2),(100,10,24),(1000,100,96)]],
      'shot_sensitivity':[{'assumed_optimum_probability':p,'shots_for_95_percent_hit':shots_for_hit(p)}
                          for p in [10/4096,0.00886,1e-3,1e-6,1e-9]],
      'caveats':['Logical qubits are not physical-qubit estimates.',
        'Statevector RAM is simulator storage, not the RAM of the best classical solver.',
        'Hypothetical success probabilities are not predictions as fleet size grows.',
        'The fixed50kW budget remains a physical bottleneck as cars/docks are added.']}


if __name__=='__main__':
    import json
    print(json.dumps(projections(),indent=2))
