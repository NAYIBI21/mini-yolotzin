/* Avisos de movilidad colaborativos (sin identificar a quienes reportan).
   Información no verificada; distinta de la afluencia diaria pronosticada. */
(() => {
  'use strict';
  const cloud = window.MINI_YOLOTZIN_CLOUD;
  const router = window.MINI_YOLOTZIN_ROUTER;
  if (!cloud?.api || !router?.reportSignals) return;
  const make = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const panels = [];
  for (const [viewId, location] of [['routesView', 'after-intro'], ['mapView', 'append']]) {
    const view = document.getElementById(viewId);
    if (!view) continue;
    const card = make('section', undefined, 'card-block');
    card.setAttribute('aria-label', 'Avisos ciudadanos recientes');
    card.style.marginBlock = '12px';
    card.style.padding = '14px';
    const title = make('h3', 'Pulso ciudadano · últimos 30 minutos');
    title.style.margin = '0 0 8px';
    const status = make('p', 'Conectando con reportes…');
    status.style.margin = '0 0 8px';
    status.setAttribute('role', 'status');
    const list = make('ul');
    list.style.paddingLeft = '20px';
    list.style.margin = '0';
    const source = make('p', 'Avisos de usuarios, sin verificar. No son mediciones de ocupación ni sustituyen los avisos oficiales.');
    source.style.fontSize = '.8rem';
    source.style.opacity = '.85';
    source.style.marginTop = '8px';
    card.append(title, status, list, source);
    if (location === 'after-intro') {
      const intro = view.querySelector('.planner-intro');
      if (intro) intro.after(card); else view.prepend(card);
    } else {
      (view.querySelector('.tab-inner') || view).append(card);
    }
    panels.push({ status, list });
  }
  if (!panels.length) return;
  let loading = false, lastSuccess = 0, timer = null, realtime = 'Conectando';
  const setStatus = text => panels.forEach(p => { p.status.textContent = text; });
  const render = reports => {
    const byStation = new Map();
    const signals = router.reportSignals(reports);
    for (const report of reports) {
      if (!report?.estacion || !report?.linea) continue;
      const id = String(report.linea) + '|' + router.key(report.estacion);
      if (!signals.has(id)) continue;
      const prev = byStation.get(id);
      if (!prev || Date.parse(report.creado_en) > Date.parse(prev.creado_en)) byStation.set(id, report);
    }
    const ranked = [...byStation].map(([id, report]) => ({ report, signal: signals.get(id) }))
      .sort((a, b) => b.signal.penalty - a.signal.penalty).slice(0, 6);
    for (const panel of panels) {
      panel.list.replaceChildren();
      if (!ranked.length) {
        panel.list.append(make('li', 'Sin avisos de incidencia recientes. Esto no confirma que el servicio esté normal.'));
      } else {
        for (const { report, signal } of ranked) {
          const type = Array.isArray(report.tipos) ? report.tipos.filter(Boolean).join(', ').replaceAll('_', ' ') : '';
          const level = report.afluencia === 'lleno' ? 'saturación reportada' :
            report.afluencia === 'vacio' ? 'poca gente reportada' : 'aviso ciudadano';
          const age = Math.max(0, Math.floor((Date.now() - Date.parse(report.creado_en)) / 60000));
          panel.list.append(make('li', report.estacion + ' · L' + report.linea + ': ' +
            (type || level) + ' · ' + signal.count + ' reporte(s) · hace ' + age + ' min'));
        }
      }
    }
  };
  async function refresh() {
    if (loading || document.visibilityState === 'hidden') return;
    loading = true;
    if (!navigator.onLine) {
      setStatus('Sin conexión · los avisos no están disponibles.');
      loading = false;
      return;
    }
    try {
      const response = await cloud.api('avisos-ruta');
      if (!response?.ok || !Array.isArray(response.data?.avisos)) throw Error('consulta fallida');
      lastSuccess = Date.now();
      render(response.data.avisos);
      setStatus(realtime + ' · Consulta actualizada a las ' +
        new Date(lastSuccess).toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' }) +
        ' · ' + response.data.avisos.length + ' avisos recientes');
    } catch (_) {
      setStatus('No se pudieron actualizar los avisos. El modelo histórico sigue disponible.');
    } finally { loading = false; }
  }
  const schedule = () => {
    clearTimeout(timer);
    timer = setTimeout(refresh, 300);
  };
  window.addEventListener('online', schedule);
  window.addEventListener('offline', () => setStatus('Sin conexión · reportes no disponibles.'));
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') schedule();
  });
  cloud.listen(() => { realtime = 'Aviso recibido en vivo'; schedule(); }, 'mini-yolotzin-pulso-publico');
  setInterval(refresh, 30000);
  refresh();
})();
