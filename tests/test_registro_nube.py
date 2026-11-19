"""Prueba de la pantalla de usuario/contraseña con Supabase simulado.

No crea usuarios ni reportes reales ni necesita internet. El servicio externo
se reemplaza para comprobar el flujo en un navegador Chromium real.
"""
from __future__ import annotations

import json


FAKE_SUPABASE = r"""
window.supabase = {
  createClient: () => {
    let user = null;
    const reports = [];
    class Query {
      constructor(table) { this.table = table; this.filters = []; this.n = 100; }
      select() { return this; }
      eq(key, value) { this.filters.push(row => row[key] === value); return this; }
      gte(key, value) { this.filters.push(row => row[key] >= value); return this; }
      order() { return this; }
      limit(n) { this.n = n; return this; }
      upsert() { return Promise.resolve({ error: null }); }
      insert(body) {
        if (this.table === 'incidencias') {
          reports.push({ afluencia: body.afluencia, tipos: body.tipos, estacion: body.estacion,
            linea: body.linea, creado_en: new Date().toISOString() });
        }
        return Promise.resolve({ error: null });
      }
      then(resolve, reject) {
        const data = this.table === 'avisos_realtime'
          ? reports.filter(row => this.filters.every(fn => fn(row))).slice(0, this.n) : [];
        return Promise.resolve({ data, error: null }).then(resolve, reject);
      }
    }
    return {
      auth: {
        getUser: async () => ({ data: { user }, error: null }),
        signInWithPassword: async ({ email }) => {
          user = { id: 'usuario-de-prueba', email };
          return { data: { user }, error: null };
        },
        signOut: async () => { user = null; return { error: null }; },
      },
      from: table => new Query(table),
      channel: () => ({ on() { return this; }, subscribe() { return this; } }),
      removeChannel: () => {},
    };
  },
};
"""


def test_registro_sin_correo_en_navegador(browser, site_url):
    context = browser.new_context(viewport={"width": 390, "height": 844})
    context.route("https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.57.0/dist/umd/supabase.js",
                  lambda route: route.fulfill(status=200, content_type="text/javascript",
                                              body=FAKE_SUPABASE))
    context.route("https://gcqubevzbqvaaxepbaba.supabase.co/functions/v1/registrar-usuario",
                  lambda route: route.fulfill(status=200, content_type="application/json",
                                              headers={"Access-Control-Allow-Origin": "*",
                                                       "Access-Control-Allow-Headers": "apikey, content-type"},
                                              body=json.dumps({"ok": True, "usuario": "ana123"})))
    page = context.new_page()
    page.set_default_timeout(10000)
    page.goto(site_url + "?cloud=1")
    assert page.is_visible("#accountUser")
    assert not page.is_visible("#profileForm")
    assert not page.is_visible("#noAccountButton")
    assert page.locator("#accountUser").get_attribute("type") == "text"
    page.click("#registerButton")
    assert page.text_content("#accountTitle") == "Crear cuenta"
    page.fill("#accountUser", "ana123")
    page.fill("#accountPassword", "clave-segura-123")
    page.fill("#accountPasswordConfirm", "clave-segura-123")
    page.click('#accountForm button[type="submit"]')
    page.wait_for_selector("#profileOverlay.hidden")
    assert page.text_content("#profileDisplayName") == "ana123"
    page.click("#tab-explore")
    page.select_option("#stationSelect", "2|Hidalgo")
    page.click("#reportButton")
    page.click('.report-level[data-level="lleno"]')
    page.click('.incident[data-incident="retraso"]')
    page.click("#reportSend")
    page.wait_for_function("document.querySelector('#reportMessage').textContent.includes('Gracias')")
    assert "Mayoría: lleno" in page.text_content("#reportSummary")
    assert "Trenes lentos" in page.text_content("#reportSummary")
    context.close()
