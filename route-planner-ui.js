/* Presentación del planificador: UI independiente del login, viajes y mapa. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const graphLib = window.MINI_YOLOTZIN_ROUTER;
  const catalog = window.METRO_CATALOG?.stations;
  const gtfs = window.MINI_YOLOTZIN_GTFS;
  const model = window.MINI_YOLOTZIN_DATA;
  const results = $('routesResults'), message = $('routesMessage');
  if (!results || !graphLib || !catalog || !model || !gtfs) {
    if (message) message.textContent = 'No se pudo cargar el planificador. Actualiza la aplicación.';
    return;
  }
  const lineLabel = line => 'Línea ' + line;
  const opt = (name, value) => { const item = document.createElement('option');
    item.value = value; item.textContent = name; return item; };
  const names = graphLib.buildGraph(catalog, gtfs).names;
  for (const n of names) {
    $('routesFrom').append(opt(n.name, n.name));
    $('routesTo').append(opt(n.name, n.name));
  }
  const preferred = (name, fallback) => names.find(n => n.name === name)?.name || fallback;
  $('routesFrom').value = preferred('Hidalgo', names[0]?.name);
  $('routesTo').value = preferred('Pantitlán', names[1]?.name);
  const initialText = 'Elige tu origen y destino para comparar rutas con tiempos GTFS y afluencia prevista.';
  message.textContent = initialText;

  let lastRequest = 0, lastInputs = null, alreadySearched = false;
  const make = (tag, cls, text) => {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (text !== undefined) el.textContent = text;
    return el;
  };
  const modeLabel = {
    rapida: 'Llegar más rápido',
    tranquila: 'Evitar mayor afluencia',
    equilibrada: 'Equilibrar tiempo y afluencia'
  };
  const dateState = () => {
    const start = model.dataset?.forecastStart;
    const max = model.dataset?.forecastDays;
    const value = $('dateInput')?.value || new Date().toISOString().slice(0, 10);
    const index = Math.round((Date.parse(value + 'T00:00:00Z') - Date.parse(start + 'T00:00:00Z')) / 86400000);
    const day = new Date(value + 'T12:00:00Z').getUTCDay();
    return { date: value, index: index >= 0 && index < max ? index : null,
      service: day === 0 ? '3' : day === 6 ? '2' : '1' };
  };
  function renderRoute(route, best, i) {
    const item = make('article', 'planner-route' + (route === best ? ' recommended' : ''));
    const top = make('div', 'planner-route-head');
    const heading = make('div', '');
    heading.append(make('strong', '', route === best ? 'Ruta recomendada' : 'Alternativa ' + (i + 1)));
    if (route === best) heading.append(make('span', 'planner-tag', 'Para tu preferencia'));
    const duration = make('div', 'planner-duration', '≈ ' + route.minutes + ' min');
    top.append(heading, duration);
    item.append(top);
    item.append(make('p', 'planner-meta', route.stops + ' estaciones entre origen y destino · ' +
      route.transfers + ' transbordo' + (route.transfers === 1 ? '' : 's') +
      ' · Afluencia diaria prevista: ' + route.demand.toLowerCase()));
    const ordered = make('ol', 'planner-legs');
    for (const leg of route.legs) {
      const li = make('li', '');
      const badge = make('span', 'planner-line', 'L' + leg.line);
      badge.setAttribute('aria-label', lineLabel(leg.line));
      const info = make('span', 'planner-leg-text', leg.from + ' → ' + leg.to);
      const stops = make('small', '', leg.stops + ' tramo' + (leg.stops === 1 ? '' : 's'));
      li.append(badge, info, stops);
      ordered.append(li);
    }
    item.append(ordered);
    if (route.alerts.length) {
      const warning = make('p', 'planner-warning', 'Avisos recientes sin verificar: ' +
        route.alerts.slice(0, 3).map(a => a.name + ' (L' + a.line + ')').join(', ') + '.');
      item.append(warning);
    }
    return item;
  }
  async function loadSharedReports() {
    if (!window.MINI_YOLOTZIN_CLOUD?.api) return { reports: [], status: 'Sin conexión a avisos compartidos en esta versión.' };
    const response = await window.MINI_YOLOTZIN_CLOUD.api('avisos-ruta').catch(() => null);
    if (!response?.ok || !Array.isArray(response.data?.avisos))
      return { reports: [], status: 'Avisos no disponibles. Se comparan solo las estimaciones históricas.' };
    return { reports: response.data.avisos, status: response.data.avisos.length ?
      response.data.avisos.length + ' avisos ciudadanos recientes considerados (sin verificar).' :
      'Sin avisos recientes; se usan las estimaciones diarias.' };
  }
  async function plan() {
    const from = $('routesFrom').value, to = $('routesTo').value;
    if (from === to) {
      message.textContent = 'Selecciona dos estaciones diferentes.';
      results.replaceChildren();
      return;
    }
    const requestId = ++lastRequest;
    message.textContent = 'Comparando conexiones del Metro…';
    results.replaceChildren();
    const date = dateState(), alertData = await loadSharedReports();
    if (requestId !== lastRequest) return;
    const preference = $('routesPreference').value;
    const graph = graphLib.buildGraph(catalog, gtfs, date.service);
    const routes = graphLib.findRoutes({
      graph, from, to,
      records: date.index === null ? [] : model.stations,
      dateIndex: date.index ?? 0,
      reports: alertData.reports
    });
    if (!routes.length) {
      message.textContent = 'No encontramos una conexión de Metro para este recorrido.';
      return;
    }
    const chosen = graphLib.recommend(routes, preference);
    const ordered = [chosen, ...routes.filter(x => x !== chosen)];
    for (let i = 0; i < ordered.length; i++) results.append(renderRoute(ordered[i], chosen, i));
    message.textContent = modeLabel[preference] + ' · ' + alertData.status +
      (date.index === null ? ' La fecha está fuera del horizonte de predicción de afluencia.' : '');
    alreadySearched = true;
    lastInputs = [from, to, preference, date.date];
  }
  $('routesForm').addEventListener('submit', event => { event.preventDefault(); plan(); });
  $('routesSwap').addEventListener('click', () => {
    const from = $('routesFrom').value; $('routesFrom').value = $('routesTo').value;
    $('routesTo').value = from;
    if (alreadySearched) plan();
  });
  $('routesFrom').addEventListener('change', () => { if (alreadySearched) plan(); });
  $('routesTo').addEventListener('change', () => { if (alreadySearched) plan(); });
  $('routesPreference').addEventListener('change', () => { if (alreadySearched) plan(); });
  $('dateInput')?.addEventListener('change', () => { if (alreadySearched) plan(); });
  if (window.MINI_YOLOTZIN_CLOUD?.listen) {
    window.MINI_YOLOTZIN_CLOUD.listen(() => {
      if (document.body.dataset.view === 'routes' && alreadySearched) plan();
    });
  }
  setInterval(() => {
    if (document.visibilityState === 'visible' && document.body.dataset.view === 'routes' && alreadySearched)
      plan();
  }, 30000);
})();
