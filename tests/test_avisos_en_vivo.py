"""Pruebas de la capa ciudadana: reportes no verificados y actualización visual."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_paneles_cargan_en_rutas_y_mapa(page):
    # En localhost la app usa perfiles locales. Inicializa el panel con una respuesta de nube simulada.
    page.evaluate("""() => {
        window.MINI_YOLOTZIN_CLOUD = {
            api: async () => ({ok: true, data: {avisos: []}}),
            listen() {},
        };
    }""")
    page.add_script_tag(url="./live-reports.js")
    page.click("#tab-routes")
    assert page.locator("#routesView [aria-label='Avisos ciudadanos recientes']").count() == 1
    assert page.locator("#mapView [aria-label='Avisos ciudadanos recientes']").count() == 1
    assert "sin verificar" in page.locator(
        "#routesView [aria-label='Avisos ciudadanos recientes']"
    ).text_content().lower()


def test_pwa_incluye_panel_ciudadano():
    sw = (ROOT / "sw.js").read_text(encoding="utf-8")
    index = (ROOT / "index.html").read_text(encoding="utf-8")
    assert "'./live-reports.js'" in sw
    assert '<script src="./live-reports.js"></script>' in index


def test_reportes_recientes_pesan_mas_y_caducan(page):
    result = page.evaluate("""() => {
      const router = window.MINI_YOLOTZIN_ROUTER;
      const now = Date.parse('2026-11-19T20:00:00Z');
      const report = mins => [{
        estacion: 'Hidalgo', linea: '2', afluencia: 'lleno',
        tipos: ['tren_detenido'],
        creado_en: new Date(now - mins * 60000).toISOString()
      }];
      const signal = reports => router.reportSignals(reports, now).get('2|hidalgo');
      return {
        fresh: signal(report(1))?.penalty,
        old: signal(report(25))?.penalty,
        stale: signal(report(35)),
        corroborated: signal([...report(1), ...report(2), ...report(3)])?.penalty,
        capped: signal(Array.from({length: 50}, () => report(0)[0]))?.penalty,
        invalid: signal([{estacion:'Hidalgo', linea:'2', afluencia:'lleno',
          creado_en:'not-a-date'}])
      };
    }""")
    assert result["fresh"] > result["old"] > 0
    assert result["stale"] is None
    assert result["corroborated"] > result["fresh"]
    assert result["capped"] == 7
    assert result["invalid"] is None
