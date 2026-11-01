export function optionsAt(fixture, weight = 0.25) {
  return fixture.options.map((booking, index) => ({ ...booking, index,
    score: booking.electricity_cost_rupees + weight * booking.waiting_minutes }));
}

export function scheduleAt(fixture, weight = 0.25) {
  const options = optionsAt(fixture, weight);
  const groups = fixture.scenario.vehicles.map(car => options.filter(o => o.vehicle_id === car.id));
  let combinations = [[]];
  for (const group of groups) combinations = combinations.flatMap(previous => group.map(o => [...previous, o]));
  const candidates = combinations.map(bookings => {
    const resources = bookings.map(o => o.station_id + '/' + o.slot_id);
    const valid = new Set(resources).size === resources.length;
    return { bookings, valid, cost: bookings.reduce((s,o) => s + o.electricity_cost_rupees, 0),
      waiting: bookings.reduce((s,o) => s + o.waiting_minutes, 0),
      score: bookings.reduce((s,o) => s + o.score, 0) };
  });
  let best = null;
  for (const candidate of candidates) if (candidate.valid && (!best || candidate.score < best.score)) best = candidate;
  return { options, candidates, best };
}

export function safePenalty(options) {
  const maxima = new Map();
  for (const option of options) maxima.set(option.vehicle_id, Math.max(maxima.get(option.vehicle_id) ?? 0, option.score));
  return [...maxima.values()].reduce((sum, cost) => sum + cost, 1);
}

export function energyOf(bits, options, penalty = safePenalty(options)) {
  const selected = Array.from(bits, Number);
  const a = selected.slice(0,4).reduce((s,x) => s+x, 0);
  const constraint = (a-1)**2 + (selected[4]-1)**2 + selected[0]*selected[4];
  const objective = options.reduce((s,o,i) => s + o.score * selected[i],0);
  return { bits, objective, penalty: penalty * constraint, energy: objective + penalty * constraint,
    feasible: constraint === 0, selected: options.filter((o,i) => selected[i]),
    reasons: [a!==1 && 'Car A needs exactly one booking.', selected[4]!==1 && 'Car B needs its North/early booking.',
      selected[0]*selected[4] && 'Both cars reserve North/early.'].filter(Boolean) };
}

export function encodedStates(options) {
  return Array.from({length:32},(_,i) => energyOf(i.toString(2).padStart(5,'0'),options));
}
