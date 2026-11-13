"""La página en un navegador real (Chromium), servida por http como en GitHub Pages.

Cubre las comprobaciones mínimas de AGENTS.md. Las fechas se fijan explícitamente
para no depender del día en que se corran las pruebas.
"""

from __future__ import annotations

import pytest

from conftest import model_value, set_date

pytestmark = pytest.mark.pagina


def test_loads_with_model_and_map(page, model_data):
    assert page.text_content("#detailName") == model_data["featured"][0]["name"]
    assert page.locator("#networkViewport .station").count() == 163
    assert page.locator("#stationSelect option").count() == len(model_data["stations"])


def test_tabs_with_keyboard(page):
    page.focus("#tab-explore")
    page.keyboard.press("ArrowRight")
    assert page.is_visible("#methodView")
    assert page.get_attribute("#tab-method", "aria-selected") == "true"
    page.keyboard.press("End")
    assert page.is_visible("#dataView")
    assert page.locator("#stationTable tr").count() == 195
    page.keyboard.press("Home")
    assert page.is_visible("#exploreView")


def test_station_and_date_show_model_value(page, model_data):
    page.select_option("#stationSelect", "3|Hidalgo")
    set_date(page, "2026-11-17")
    expected = model_value(model_data, "3", "Hidalgo", "2026-11-17")
    assert page.text_content("#detailEstimate") == f"{expected:,}"
    page.click('#detailLines button[data-line="2"]')
    expected_l2 = model_value(model_data, "2", "Hidalgo", "2026-11-17")
    assert page.text_content("#detailEstimate") == f"{expected_l2:,}"


def test_holiday_and_event_notes(page):
    set_date(page, "2026-11-16")
    assert "Revolución" in page.text_content("#calendarChip")
    page.select_option("#stationSelect", "9|Ciudad Deportiva")
    set_date(page, "2026-11-01")
    assert page.is_visible("#eventChip")
    note = page.text_content("#eventNote")
    assert "Gran Premio" in note and "Sin el evento" in note


def test_search_and_line_filter(page):
    page.fill("#mapSearch", "zocalo")
    assert page.locator("#mapStationList option").count() == 1
    page.fill("#mapSearch", "")
    page.select_option("#mapLineFilter", "A")
    assert page.locator("#mapStationList option").count() == 10


def test_map_playback_and_zoom(page):
    before = page.text_content("#dateLabel")
    page.click("#playPause")
    page.wait_for_timeout(1900)
    page.click("#playPause")
    assert page.text_content("#dateLabel") != before
    transform = page.get_attribute("#networkViewport", "transform")
    page.click("#zoomIn")
    assert page.get_attribute("#networkViewport", "transform") != transform


def test_week_view_skips_holiday(page):
    set_date(page, "2026-11-13")
    assert page.locator("#weekGrid .week-day").count() == 7
    best = page.get_attribute("#weekGrid .week-day.best", "aria-label")
    assert "16 nov" not in best                     # el lunes festivo no cuenta como día hábil
    page.click("#weekGrid .week-day >> nth=3")
    assert page.input_value("#dateInput") == "2026-11-16"


def test_my_trips_persist_and_escape_text(page):
    page.click("#saveStation")
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


def test_profile_dialog_escape_returns_focus(page):
    page.click("#profileButton")
    assert page.is_visible("#profileOverlay")
    page.keyboard.press("Escape")
    assert not page.is_visible("#profileOverlay")
    assert page.evaluate("document.activeElement.id") == "profileButton"


def test_works_offline_after_first_visit(page):
    page.evaluate("navigator.serviceWorker.ready.then(() => true)")
    page.reload()
    page.wait_for_timeout(500)
    page.context.set_offline(True)
    page.reload()
    assert page.locator("#networkViewport .station").count() == 163
    page.context.set_offline(False)


@pytest.mark.parametrize("width", [1024, 390])
def test_no_horizontal_scroll(page, width):
    page.set_viewport_size({"width": width, "height": 844})
    page.wait_for_timeout(150)
    assert page.evaluate("document.documentElement.scrollWidth") <= width
