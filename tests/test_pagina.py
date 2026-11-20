"""La página en un navegador real (Chromium), servida por http como en GitHub Pages.

Cubre las comprobaciones mínimas de AGENTS.md. Las fechas se fijan explícitamente
para no depender del día en que se corran las pruebas.
"""

from __future__ import annotations

import re

import pytest

from conftest import model_value, set_date

pytestmark = pytest.mark.pagina


def go(page, view: str) -> None:
    """Cambia de pestaña: today (Hoy), explore (Estaciones), map (Mapa) o agenda."""
    page.click(f"#tab-{view}")


def test_loads_with_model_and_map(page, model_data):
    assert page.text_content("#detailName") == model_data["featured"][0]["name"]
    assert page.locator("#networkViewport .station").count() == 163
    assert page.locator("#stationSelect option").count() == len(model_data["stations"])


def test_opens_on_today(page, model_data):
    from datetime import date
    today = date.today().isoformat()
    in_range = model_data["dataset"]["forecastStart"] <= today <= model_data["dataset"]["forecastEnd"]
    if in_range:
        assert page.input_value("#dateInput") == today
        assert page.text_content("#dateLabel").startswith("Hoy")
    set_date(page, "2026-12-03")
    page.click("#resetDate")                               # el botón «Hoy» regresa al día de hoy
    if in_range:
        assert page.input_value("#dateInput") == today


def test_tabs_with_keyboard(page):
    assert page.is_visible("#todayView")                  # la app abre en Hoy
    page.focus("#tab-today")
    page.keyboard.press("ArrowRight")
    assert page.is_visible("#exploreView")
    assert page.get_attribute("#tab-explore", "aria-selected") == "true"
    page.keyboard.press("End")
    assert page.is_visible("#agendaView")
    page.keyboard.press("ArrowLeft")
    assert page.is_visible("#mapView")
    page.keyboard.press("Home")
    assert page.is_visible("#todayView")


def test_method_and_data_pages_from_station(page):
    go(page, "explore")
    page.click("#openData")
    assert page.is_visible("#dataView")
    assert page.locator("#stationTable tr").count() == 195
    assert not page.is_visible(".datebar")
    page.click("#dataView .back-btn")
    page.click("#openMethod")
    assert page.is_visible("#methodView")
    page.click("#methodView .back-btn")
    assert page.is_visible("#exploreView")


def test_station_and_date_show_model_value(page, model_data):
    go(page, "explore")
    page.select_option("#stationSelect", "3|Hidalgo")
    set_date(page, "2026-11-17")
    expected = model_value(model_data, "3", "Hidalgo", "2026-11-17")
    assert page.text_content("#detailEstimate") == f"{expected:,}"
    assert f"{expected:,} entradas" in page.text_content("#riskEstimate")
    assert page.text_content("#riskText") in ("Más gente de lo normal", "Lo normal", "Menos gente de lo normal")
    page.click('#detailLines button[data-line="2"]')
    expected_l2 = model_value(model_data, "2", "Hidalgo", "2026-11-17")
    assert page.text_content("#detailEstimate") == f"{expected_l2:,}"


def test_holiday_and_event_notes(page):
    set_date(page, "2026-11-16")
    assert "Revolución" in page.text_content("#todayNotices")
    assert not page.is_visible("#calendarChip")                   # en Hoy no se repite en la barra de fecha
    go(page, "explore")
    assert "Revolución" in page.text_content("#calendarChip")
    page.select_option("#stationSelect", "9|Ciudad Deportiva")
    set_date(page, "2026-11-01")
    assert page.is_visible("#eventChip")
    go(page, "today")
    assert not page.is_visible("#eventChip")
    assert page.locator("#todayNotices .notice.evt").count() == 1
    go(page, "explore")
    note = page.text_content("#eventNote")
    assert "Gran Premio" in note and "Sin el evento" in note


def test_search_and_line_filter(page):
    go(page, "explore")
    page.fill("#mapSearch", "zocalo")
    assert page.locator("#mapStationList option").count() == 1
    page.fill("#mapSearch", "")
    page.select_option("#mapLineFilter", "A")
    assert page.locator("#mapStationList option").count() == 10


def test_map_playback_and_zoom(page):
    go(page, "map")
    before = page.text_content("#dateLabel")
    page.click("#playPause")
    page.wait_for_timeout(1900)
    page.click("#playPause")
    assert page.text_content("#dateLabel") != before
    transform = page.get_attribute("#networkViewport", "transform")
    page.click("#zoomIn")
    assert page.get_attribute("#networkViewport", "transform") != transform


def test_map_sheet_follows_station(page, model_data):
    go(page, "explore")
    page.select_option("#stationSelect", "3|Hidalgo")
    set_date(page, "2026-11-17")
    go(page, "map")
    assert page.text_content("#sheetName") == "Hidalgo"
    expected = model_value(model_data, "3", "Hidalgo", "2026-11-17")
    assert page.text_content("#sheetEstimate") == f"~{expected:,}"
    page.click("#sheetOpen")
    assert page.is_visible("#exploreView")


def test_week_view_skips_holiday(page):
    go(page, "explore")
    set_date(page, "2026-11-13")
    assert page.locator("#weekGrid .week-day").count() == 7
    best = page.get_attribute("#weekGrid .week-day.best", "aria-label")
    assert "16 nov" not in best                     # el lunes festivo no cuenta como día hábil
    page.click("#weekGrid .week-day >> nth=3")
    assert page.input_value("#dateInput") == "2026-11-16"


def test_my_trips_persist_and_escape_text(page):
    go(page, "explore")
    page.click("#saveStation")
    go(page, "today")
    page.click("#tripAddToggle")
    page.fill("#tripLabel", "<b>Casa</b> → Escuela")
    page.select_option("#tripFrom", "3|Indios Verdes")
    page.select_option("#tripTo", "3|Universidad")
    page.click("#tripForm button[type=submit]")
    assert page.locator(".trip-item").count() == 2
    assert page.locator(".trip-item b").count() == 0          # el nombre se muestra como texto
    page.reload()
    assert page.locator(".trip-item").count() == 2
    page.click(".trip-item >> nth=0 >> .trip-remove")
    assert page.locator(".trip-item").count() == 1
    page.click(".trip-item .trip-stop >> nth=0")         # tocar una parada abre su ficha
    assert page.is_visible("#exploreView")
    assert page.text_content("#detailName") == "Indios Verdes"


def test_agenda_lists_events_and_filters(page):
    go(page, "agenda")
    assert page.locator("#agendaList .agenda-day").count() > 0
    page.click('#agendaFilters [data-filter="cal"]')
    assert page.locator("#agendaList .notice.evt").count() == 0
    page.click('#agendaFilters [data-filter="mine"]')      # sin estaciones guardadas no hay nada propio
    assert page.locator("#agendaList .notice").count() == 0


def test_login_screen_like_the_design(browser, site_url):
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    page.goto(site_url)
    assert page.text_content("#profileOverlay h2") == "Mini Yolotzin"
    assert page.is_visible("#profilePrivacy")
    context.close()


def test_profile_dialog_escape_returns_focus(page):
    page.click("#profileButton")
    assert page.is_visible("#profileOverlay")
    page.keyboard.press("Escape")
    assert not page.is_visible("#profileOverlay")
    assert page.evaluate("document.activeElement.id") == "profileButton"


def test_works_offline_after_first_visit(page):
    # Con límite propio: si la página falla, el service worker nunca se registra y esto no debe colgarse.
    registered = page.evaluate("Promise.race([navigator.serviceWorker.ready.then(() => true), new Promise(r => setTimeout(() => r(false), 5000))])")
    assert registered, "El service worker no se registró"
    page.reload()
    page.wait_for_timeout(500)
    page.context.set_offline(True)
    page.reload()
    assert page.locator("#networkViewport .station").count() == 163
    page.context.set_offline(False)


def test_ecobici_live_near_station(page):
    go(page, "explore")
    page.select_option("#stationSelect", "3|Hidalgo")
    page.wait_for_selector("#bikeList .bike-item")
    items = page.locator("#bikeList .bike-item").all_text_contents()
    assert len(items) == 2                               # la tercera está a más de 500 m
    text = " | ".join(items)
    assert "Prueba Uno" in text and "7 bicis · 12 espacios" in text
    assert "1 bici · 19 espacios" in text                  # singular
    assert "CE-90" not in text                             # sin el código interno
    distances = [int(re.search(r"(\d+) m ·", item).group(1)) for item in items]
    assert distances == sorted(distances)                  # de la más cercana a la más lejana
    assert "no es una estimación del modelo" in page.text_content("#bikeNote")
    page.select_option("#stationSelect", "3|Indios Verdes")
    assert page.locator("#bikeList .bike-item").count() == 0
    assert "No hay cicloestaciones" in page.text_content("#bikeNote")


def test_ecobici_failure_keeps_page_working(page, model_data):
    page.context.ecobici_mode = "fail"
    page.reload()
    page.wait_for_function("!document.getElementById('bikeNote').textContent.includes('Consultando')")
    assert "Ecobici no respondió" in page.text_content("#bikeNote")
    assert page.text_content("#detailEstimate") != "—"   # el modelo se sigue mostrando


@pytest.mark.parametrize("width", [1024, 390])
def test_no_horizontal_scroll(page, width):
    page.set_viewport_size({"width": width, "height": 844})
    page.wait_for_timeout(150)
    assert page.evaluate("document.documentElement.scrollWidth") <= width


def test_today_weather_and_event_icons(page):
    page.click("#resetDate")                                        # hoy: hay pronóstico de prueba
    page.wait_for_function("document.getElementById('weatherTitle').textContent.includes('°C')")
    assert page.text_content("#weatherTitle") == "19 °C · lluvia (80%)"
    assert "casi no cambia" in page.text_content("#weatherText")
    assert page.get_attribute("#weatherIcon svg", "viewBox") == "0 0 24 24"
    set_date(page, "2026-12-03")                                    # concierto de Bruno Mars en el Estadio GNP
    concert = page.locator('#todayNotices .notice[data-icon="concierto"]')
    assert concert.count() >= 1 and "Estadio GNP" in concert.first.text_content()
    set_date(page, "2026-12-12")
    assert page.locator('#todayNotices .notice[data-icon="festivo"]').count() == 1


def test_weather_failure_keeps_today_working(page):
    page.context.weather_mode = "fail"
    page.reload()
    page.wait_for_function("document.getElementById('weatherText').textContent.includes('Sin pronóstico')")
    assert page.text_content("#weatherTitle") == "Clima"


def test_greeting_hides_email_domain(page):
    page.evaluate("""() => { const p = JSON.parse(localStorage.getItem('mini_yolotzin_profile_v1'));
        p.name = 'karen@ejemplo.com'; localStorage.setItem('mini_yolotzin_profile_v1', JSON.stringify(p)); }""")
    page.reload()
    assert page.text_content("#todayGreeting") == "Hola, karen."
