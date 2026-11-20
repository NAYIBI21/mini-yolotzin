/* Mini Yolotzin: rutas orientativas, no tiempos oficiales del Metro.
   Supuestos académicos: 2.4 min por tramo, 6 min por transbordo y
   3 min de espera al inicio. La afluencia estimada es DIARIA. */
(function (root) {
  'use strict';
  const RIDE = 2.4, TRANSFER = 6, WAIT = 3;
  const key = name => String(name || '').split('/')[0].normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]/g, '');

  function buildGraph(stations) {
    const nodes = new Map(), edges = new Map(), byName = new Map(), byLine = new Map();
    (stations || []).forEach(s => {
      if (!s?.id || !s?.name || !s?.line) return;
      const id = String(s.id), k = key(s.name), line = String(s.line);
      nodes.set(id, { id, name: s.name, key: k, line });
      edges.set(id, []);
      if (!byName.has(k)) byName.set(k, []);
      byName.get(k).push(id);
      if (!byLine.has(line)) byLine.set(line, []);
      byLine.get(line).push(id);
    });
    const link = (a, b, type, minutes) => {
      edges.get(a).push({ to: b, type, minutes });
      edges.get(b).push({ to: a, type, minutes });
    };
    // La lista oficial guarda las estaciones en orden de recorrido de cada línea.
    byLine.forEach(ids => { for (let i = 1; i < ids.length; i++)
      link(ids[i - 1], ids[i], 'ride', RIDE); });
    byName.forEach(ids => { for (let i = 0; i < ids.length; i++)
      for (let j = i + 1; j < ids.length; j++)
        if (nodes.get(ids[i]).line !== nodes.get(ids[j]).line)
          link(ids[i], ids[j], 'transfer', TRANSFER); });
    const names = [...byName].map(([k, ids]) => ({
      key: k, name: nodes.get(ids[0]).name, lines: ids.map(id => nodes.get(id).line)
    })).sort((a, b) => a.name.localeCompare(b.name, 'es'));
    return { nodes, edges, byName, names };
  }

  function crowdRisks(records, index, reports) {
    const risk = new Map(), flagged = new Map();
    (records || []).forEach(r => {
      const p = r?.predictions?.[index];
      if (!Number.isFinite(p) || !r.summary) return;
      const level = p < r.summary.lowThreshold ? 0.35 :
        p >= r.summary.highThreshold ? 1.75 : 0.95;
      risk.set(String(r.line) + '|' + key(r.name), level);
    });
    (reports || []).forEach(r => {
      if (!r?.linea || !r?.estacion) return;
      const k = String(r.linea) + '|' + key(r.estacion);
      const t = Array.isArray(r.tipos) ? r.tipos : [];
      const penalty = Math.max(
        r.afluencia === 'lleno' ? 2 : r.afluencia === 'normal' ? 0.6 : 0,
        t.includes('tren_detenido') ? 6 : 0,
        t.includes('acceso_cerrado') ? 5 : 0,
        t.includes('accidente') ? 5 : 0,
        t.includes('retraso') ? 3 : 0,
        t.includes('saturada') ? 2.5 : 0,
        t.includes('falla') ? 1 : 0
      );
      if (penalty) {
        risk.set(k, Math.max(risk.get(k) || 0.95, 0.95 + penalty));
        flagged.set(k, (flagged.get(k) || 0) + 1);
      }
    });
    return { risk, flagged };
  }

  function describe(graph, ids, types, live) {
    const nodes = ids.map(id => graph.nodes.get(id));
    let stops = 0, transfers = 0, sum = 0, visits = 0;
    const legs = [], seen = new Set(), alerts = [];
    let leg = { line: nodes[0].line, from: nodes[0].name, to: nodes[0].name, stops: 0 };
    for (let i = 0; i < types.length; i++) {
      const next = nodes[i + 1], type = types[i], lookup = next.line + '|' + next.key;
      if (type === 'ride') {
        stops++;
        leg.to = next.name;
        leg.stops++;
        sum += live.risk.get(lookup) || 0.95;
        visits++;
      } else {
        transfers++;
        legs.push(leg);
        leg = { line: next.line, from: next.name, to: next.name, stops: 0 };
      }
      if (live.flagged.has(lookup) && !seen.has(lookup)) {
        seen.add(lookup);
        alerts.push({ name: next.name, line: next.line, count: live.flagged.get(lookup) });
      }
    }
    legs.push(leg);
    const minutes = Math.round(stops * RIDE + transfers * TRANSFER + WAIT);
    const average = visits ? sum / visits : 0.95;
    return {
      ids, legs, stops, transfers, minutes, average, alerts,
      demand: average < 0.8 ? 'Menor' : average < 1.45 ? 'Moderada' : 'Mayor',
      fingerprint: legs.map(l => l.line + ':' + key(l.from) + '>' + key(l.to)).join('|')
    };
  }

  function shortest(graph, from, to, weights, live, used) {
    const starts = graph.byName.get(key(from)) || [];
    const ends = new Set(graph.byName.get(key(to)) || []);
    if (!starts.length || !ends.size) return null;
    const distances = new Map(), previous = new Map(), q = [], done = new Set();
    starts.forEach(id => { distances.set(id, 0); q.push([0, id]); });
    while (q.length) {
      q.sort((a, b) => a[0] - b[0]);
      const [cost, id] = q.shift();
      if (done.has(id) || cost > distances.get(id)) continue;
      done.add(id);
      if (ends.has(id)) {
        const ids = [id], types = [];
        let cur = id;
        while (previous.has(cur)) {
          const p = previous.get(cur);
          types.unshift(p.type);
          ids.unshift(p.id);
          cur = p.id;
        }
        return describe(graph, ids, types, live);
      }
      for (const edge of graph.edges.get(id) || []) {
        if (done.has(edge.to)) continue;
        const target = graph.nodes.get(edge.to);
        const risk = live.risk.get(target.line + '|' + target.key) || 0.95;
        const alertExtra = Math.max(0, risk - 1.75);
        const exposure = edge.type === 'ride'
          ? risk * 1.15 + alertExtra * 1.7 : risk * 0.75 + alertExtra * 0.6;
        const pair = [id, edge.to].sort().join('|');
        const novelty = used?.has(pair) ? 8 : 0;
        const next = cost + edge.minutes * weights.time + exposure * weights.crowd + novelty;
        if (next < (distances.get(edge.to) ?? Infinity)) {
          distances.set(edge.to, next);
          previous.set(edge.to, { id, type: edge.type });
          q.push([next, edge.to]);
        }
      }
    }
    return null;
  }

  function findRoutes({ graph, from, to, records, dateIndex = 0, reports = [] }) {
    if (!graph || key(from) === key(to) || !graph.byName.has(key(from)) ||
        !graph.byName.has(key(to))) return [];
    const live = crowdRisks(records, dateIndex, reports);
    const fastest = shortest(graph, from, to, { time: 1, crowd: 0 }, live, null);
    if (!fastest) return [];
    const routes = [fastest], signatures = new Set([fastest.fingerprint]);
    for (const weights of [{ time: 0.55, crowd: 3.2 }, { time: 1, crowd: 1.4 },
                           { time: 0.8, crowd: 2 }, { time: 1, crowd: 0.7 }]) {
      const r = shortest(graph, from, to, weights, live, null);
      if (r && !signatures.has(r.fingerprint)) {
        routes.push(r); signatures.add(r.fingerprint);
      }
    }
    const used = new Set();
    const register = r => { for (let i = 1; i < r.ids.length; i++)
      used.add([r.ids[i - 1], r.ids[i]].sort().join('|')); };
    routes.forEach(register);
    for (let i = 0; i < 3 && routes.length < 4; i++) {
      const r = shortest(graph, from, to, { time: 1, crowd: 1.1 }, live, used);
      if (r && !signatures.has(r.fingerprint)) {
        routes.push(r); signatures.add(r.fingerprint); register(r);
      }
    }
    return routes.filter(r => r.minutes <= fastest.minutes + 25 &&
      r.minutes <= fastest.minutes * 1.8)
      .sort((a, b) => a.minutes - b.minutes || a.average - b.average).slice(0, 4);
  }

  function recommend(routes, preference) {
    if (!routes?.length) return null;
    const score = r => preference === 'tranquila'
      ? r.minutes * 0.35 + r.average * Math.max(7, r.stops * 1.5) + r.alerts.length * 3
      : preference === 'rapida' ? r.minutes
      : r.minutes + r.average * Math.max(4, r.stops * 0.85) + r.alerts.length * 2;
    return routes.slice().sort((a, b) => score(a) - score(b) ||
      a.minutes - b.minutes)[0];
  }
  root.MINI_YOLOTZIN_ROUTER = { buildGraph, findRoutes, recommend, key };
})(window);
