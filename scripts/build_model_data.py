"""Build the compact browser dataset used by the Mini Yolotzin demo.

The raw CSV is an input artifact and is intentionally not shipped with the site.
The output contains only aggregate history, validation metrics and precomputed
future estimates for every station-line record of the Metro that has enough
recent data (option A: one model per station and line, as the official
resource publishes it).

Usage:
    python scripts/build_model_data.py [ruta/al/afluencia_simple.csv] [ruta/de/salida.js]
"""

from __future__ import annotations

import json
import sys
import unicodedata
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, root_mean_squared_error


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "afluencia_simple.csv"
OUTPUT_PATH = ROOT / "model-data.js"
SOURCE_URL = (
    "https://datos.cdmx.gob.mx/dataset/f2046fd5-51b5-4876-b008-bd65d95f9a02/"
    "resource/0e8ffe58-28bb-4dde-afcd-e5f5b4de4ccb"
)
DOWNLOAD_URL = SOURCE_URL + "/download/0e8ffe58-28bb-4dde-afcd-e5f5b4de4ccb.csv"

# Estaciones destacadas de la versión original (se muestran primero en la interfaz).
FEATURED = [
    ("3", "Indios Verdes"),
    ("3", "La Raza"),
    ("3", "Hidalgo"),
    ("3", "Centro Médico"),
    ("3", "Universidad"),
]

TEST_DAYS = 180            # validación cronológica: últimos 180 días observados
FORECAST_DAYS = 366        # horizonte de pronóstico
MIN_TRAIN_DAYS = 365       # días válidos mínimos para entrenar
MIN_TEST_DAYS = 90         # días válidos mínimos para validar
MAX_STALE_DAYS = 30        # si el último dato válido es más antiguo, no se pronostica
TRAIN_START = "2023-01-01"  # se omite 2021-2022 (recuperación tras la pandemia) si hay suficiente historial
RECENT_DAYS = 365          # el último año antes del corte pesa más al entrenar
RECENT_WEIGHT = 3.0
RF_PARAMS = dict(n_estimators=160, max_depth=14, min_samples_leaf=4, random_state=42, n_jobs=-1)


def repair_mojibake(value: object) -> object:
    if not isinstance(value, str) or "Ã" not in value:
        return value
    try:
        return value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


# ---------- Calendario de México ----------
# Días de descanso obligatorio (Ley Federal del Trabajo, art. 74) y fechas con efecto
# conocido en la movilidad de la CDMX. Todas se conocen con anticipación, así que
# también sirven para el pronóstico.

def easter_sunday(year: int) -> date:
    """Domingo de Pascua (algoritmo gregoriano anónimo)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def nth_monday(year: int, month: int, n: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(7 - first.weekday()) % 7 + 7 * (n - 1))


def mexican_calendar(years: range) -> tuple[dict, dict, dict]:
    """Regresa (festivos, fechas especiales, periodos vacacionales) como {fecha: nombre}."""
    holidays, special, periods = {}, {}, {}
    for y in years:
        holidays[date(y, 1, 1)] = "Año Nuevo"
        holidays[nth_monday(y, 2, 1)] = "Día de la Constitución"
        holidays[nth_monday(y, 3, 3)] = "Natalicio de Benito Juárez"
        holidays[date(y, 5, 1)] = "Día del Trabajo"
        holidays[date(y, 9, 16)] = "Día de la Independencia"
        holidays[nth_monday(y, 11, 3)] = "Día de la Revolución"
        holidays[date(y, 12, 25)] = "Navidad"
        if (y - 2024) % 6 == 0:
            holidays[date(y, 10, 1)] = "Transmisión del Poder Ejecutivo"
        easter = easter_sunday(y)
        special[easter - timedelta(days=3)] = "Jueves Santo"
        special[easter - timedelta(days=2)] = "Viernes Santo"
        special[date(y, 11, 2)] = "Día de Muertos"
        special[date(y, 12, 12)] = "Día de la Virgen de Guadalupe"
        special[date(y, 12, 24)] = "Nochebuena"
        special[date(y, 12, 31)] = "Fin de año"
        for offset in range(-6, 8):   # Semana Santa y Semana de Pascua
            periods[easter + timedelta(days=offset)] = "Vacaciones de Semana Santa"
        for offset in range(0, 20):   # 18 de diciembre al 6 de enero
            periods[date(y, 12, 18) + timedelta(days=offset)] = "Vacaciones de invierno"
    return holidays, special, periods


CALENDAR = mexican_calendar(range(2019, 2032))


def features(dates: pd.Series | pd.DatetimeIndex, calendar: bool = True) -> pd.DataFrame:
    dates = pd.DatetimeIndex(dates)
    day_of_year = dates.day_of_year.to_numpy()
    columns = {
        "month": dates.month,
        "dow": dates.day_of_week,
        "day": dates.day,
        "weekend": (dates.day_of_week >= 5).astype(int),
        "sin_year": np.sin(2 * np.pi * day_of_year / 365.25),
        "cos_year": np.cos(2 * np.pi * day_of_year / 365.25),
    }
    if calendar:
        holidays, special, periods = CALENDAR
        days = [d.date() for d in dates]
        columns["holiday"] = [int(d in holidays) for d in days]
        columns["special"] = [int(d in special) for d in days]
        # Viernes antes de un lunes festivo (puente).
        columns["bridge"] = [int(d.weekday() == 4 and (d + timedelta(days=3)) in holidays) for d in days]
        columns["easter_break"] = [int(periods.get(d) == "Vacaciones de Semana Santa") for d in days]
        columns["winter_break"] = [int(periods.get(d) == "Vacaciones de invierno") for d in days]
    return pd.DataFrame(columns)


def calendar_labels(dates: pd.DatetimeIndex) -> dict:
    """Etiquetas para mostrar en la interfaz durante el horizonte de pronóstico."""
    holidays, special, periods = CALENDAR
    labels = {}
    for d in dates:
        day = d.date()
        parts = []
        if day in holidays:
            parts.append(f"Día festivo: {holidays[day]}")
        if day in special:
            parts.append(special[day])
        if day.weekday() == 4 and (day + timedelta(days=3)) in holidays:
            parts.append("Puente")
        if day in periods:
            parts.append(periods[day])
        if parts:
            labels[d.strftime("%Y-%m-%d")] = " · ".join(parts)
    return labels


def rounded(value: float) -> int:
    return int(round(float(value)))


def line_code(label: str) -> str:
    """'Línea 3' -> '3', 'Línea A' -> 'A'."""
    return label.replace("Línea", "").strip()


def fold(text: str) -> str:
    """Quita acentos y mayúsculas para comparar nombres."""
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn").casefold()


def unify_station_names(valid: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """El recurso oficial cambió la escritura de algunos nombres el 2023-06-01
    (p. ej. «Gómez Farías» → «Gómez Farias», «Peñón Viejo» → «Peñón viejo»).
    Dentro de cada línea, los nombres que solo difieren en acentos o mayúsculas
    se unifican con la forma que aparece primero en el tiempo."""
    first_seen = valid.groupby(["linea", "estacion"])["fecha"].min().reset_index()
    first_seen["key"] = first_seen["estacion"].map(fold)
    canonical, renamed = {}, []
    for (line, _), group in first_seen.groupby(["linea", "key"]):
        group = group.sort_values("fecha")
        target = group["estacion"].iloc[0]
        for variant in group["estacion"].iloc[1:]:
            canonical[(line, variant)] = target
            renamed.append({"line": line, "from": variant, "to": target})
    if canonical:
        keys = list(zip(valid["linea"], valid["estacion"]))
        valid = valid.assign(estacion=[canonical.get(key, key[1]) for key in keys])
    return valid, renamed


def build_record(line: str, station: str, frame: pd.DataFrame, max_date: pd.Timestamp,
                 forecast_dates: pd.DatetimeIndex) -> tuple[dict | None, dict | None]:
    """Train and validate one station-line record. Returns (record, skipped)."""
    data = frame[["fecha", "afluencia"]].sort_values("fecha").drop_duplicates("fecha", keep="last")
    zero_days = int((data["afluencia"] <= 0).sum())
    # Los días con afluencia 0 corresponden a cierres (obras, contingencias): no son demanda baja.
    data = data[data["afluencia"] > 0]
    base = {"name": station, "line": line}

    if data.empty:
        return None, {**base, "reason": "sin registros con afluencia", "lastDate": None}
    last_date = data["fecha"].max()
    if (max_date - last_date).days > MAX_STALE_DAYS:
        return None, {**base, "reason": "sin datos recientes (posible cierre)", "lastDate": last_date.strftime("%Y-%m-%d")}

    cutoff = last_date - pd.DateOffset(days=TEST_DAYS - 1)
    train_all = data[data["fecha"] < cutoff]
    test = data[data["fecha"] >= cutoff]
    if len(train_all) < MIN_TRAIN_DAYS or len(test) < MIN_TEST_DAYS:
        return None, {**base, "reason": "historial insuficiente para validar", "lastDate": last_date.strftime("%Y-%m-%d")}

    # Ventana de entrenamiento: desde 2023 si hay al menos un año de datos válidos;
    # si no (estaciones con cierres largos, p. ej. Líneas 1 y 12), todo el historial.
    recent_only = train_all[train_all["fecha"] >= TRAIN_START]
    train = recent_only if len(recent_only) >= MIN_TRAIN_DAYS else train_all
    full = data[data["fecha"] >= TRAIN_START] if len(recent_only) >= MIN_TRAIN_DAYS else data
    window_start = train["fecha"].min().strftime("%Y-%m-%d")

    def recency_weights(dates: pd.Series, reference: pd.Timestamp) -> np.ndarray:
        return np.where(dates >= reference - pd.DateOffset(days=RECENT_DAYS), RECENT_WEIGHT, 1.0)

    baseline_table = train.assign(month=train["fecha"].dt.month, dow=train["fecha"].dt.day_of_week).groupby(["month", "dow"])["afluencia"].mean()
    station_mean = float(train["afluencia"].mean())
    baseline_pred = [baseline_table.get((day.month, day.day_of_week), station_mean) for day in test["fecha"]]

    # 1) Validación: se entrena solo con el pasado y se evalúa en los últimos días observados.
    model = RandomForestRegressor(**RF_PARAMS)
    model.fit(features(train["fecha"]), train["afluencia"], sample_weight=recency_weights(train["fecha"], cutoff))
    model_pred = model.predict(features(test["fecha"]))
    # 2) Pronóstico: una vez validado, el mismo modelo se reentrena con todos los datos
    #    válidos, incluidos los más recientes, antes de estimar el horizonte futuro.
    final_model = RandomForestRegressor(**RF_PARAMS)
    final_model.fit(features(full["fecha"]), full["afluencia"], sample_weight=recency_weights(full["fecha"], last_date))
    future_pred = np.maximum(0, final_model.predict(features(forecast_dates)))

    q33, q67 = train["afluencia"].quantile([0.33, 0.67]).tolist()
    q25, median, q75 = train["afluencia"].quantile([0.25, 0.5, 0.75]).tolist()
    recent = (
        data[data["fecha"] >= last_date - pd.DateOffset(months=17)]
        .set_index("fecha")["afluencia"].resample("MS").mean().dropna()
    )

    record = {
        **base,
        "summary": {
            "mean": rounded(station_mean),
            "median": rounded(median),
            "p25": rounded(q25),
            "p75": rounded(q75),
            "lowThreshold": rounded(q33),
            "highThreshold": rounded(q67),
            "observations": int(len(data)),
            "trainStart": window_start,
            "closedDays": zero_days,
        },
        "metrics": {
            "baselineMae": rounded(mean_absolute_error(test["afluencia"], baseline_pred)),
            "baselineRmse": rounded(root_mean_squared_error(test["afluencia"], baseline_pred)),
            "modelMae": rounded(mean_absolute_error(test["afluencia"], model_pred)),
            "modelRmse": rounded(root_mean_squared_error(test["afluencia"], model_pred)),
            "testStart": test["fecha"].min().strftime("%Y-%m-%d"),
            "testEnd": test["fecha"].max().strftime("%Y-%m-%d"),
        },
        "history": [{"month": d.strftime("%Y-%m"), "value": rounded(v)} for d, v in recent.items()],
        # Alineado con dataset.forecastStart, un valor por día. El nivel (baja/media/alta)
        # se calcula en el navegador con lowThreshold/highThreshold, con la misma regla de antes.
        "predictions": [rounded(v) for v in future_pred],
    }
    return record, None


def main() -> None:
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else CSV_PATH
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else OUTPUT_PATH
    frame = pd.read_csv(csv_path, dtype={"linea": "string", "estacion": "string"})
    for column in ["mes", "linea", "estacion"]:
        if column in frame:
            frame[column] = frame[column].map(repair_mojibake)
    # El recurso oficial cambió la etiqueta “Línea” por “Linea” el 2023-06-01.
    frame["linea"] = frame["linea"].str.strip().str.replace(r"^Linea ", "Línea ", regex=True)
    frame["estacion"] = frame["estacion"].str.strip()
    frame["fecha"] = pd.to_datetime(frame["fecha"], errors="coerce")
    frame["afluencia"] = pd.to_numeric(frame["afluencia"], errors="coerce")

    nulls = {key: int(value) for key, value in frame.isna().sum().items()}
    valid = frame.dropna(subset=["fecha", "linea", "estacion", "afluencia"]).copy()
    valid, renamed = unify_station_names(valid)
    for item in renamed:
        print(f"Nombre unificado en {item['line']}: {item['from']} → {item['to']}")
    max_date = valid["fecha"].max()
    forecast_dates = pd.date_range(max_date + pd.DateOffset(days=1), periods=FORECAST_DAYS, freq="D")

    records, skipped = [], []
    groups = valid.groupby(["linea", "estacion"], sort=True)
    for index, ((line_label, station), group) in enumerate(groups, start=1):
        record, skip = build_record(line_code(line_label), station, group, max_date, forecast_dates)
        (records if record else skipped).append(record or skip)
        print(f"[{index}/{groups.ngroups}] Línea {line_code(line_label)} · {station}: {'ok' if record else skip['reason']}", flush=True)

    missing = [f"{line} {name}" for line, name in FEATURED if not any(r["line"] == line and r["name"] == name for r in records)]
    if missing:
        raise RuntimeError(f"Estaciones destacadas sin modelo: {missing}")

    payload = {
        "generatedAt": pd.Timestamp.now(tz="America/Mexico_City").isoformat(),
        "source": {
            "name": "Afluencia diaria del Metro CDMX — base simple",
            "publisher": "Secretaría de Movilidad de la Ciudad de México",
            "url": SOURCE_URL,
            "downloadUrl": DOWNLOAD_URL,
            "license": "CC BY 4.0",
        },
        "dataset": {
            "rows": int(len(frame)),
            "validRows": int(len(valid)),
            "startDate": valid["fecha"].min().strftime("%Y-%m-%d"),
            "endDate": max_date.strftime("%Y-%m-%d"),
            "lines": int(valid["linea"].nunique()),
            "stations": int(valid["estacion"].nunique()),
            "records": int(groups.ngroups),
            "modeledRecords": len(records),
            "skippedRecords": len(skipped),
            "zeroRows": int((valid["afluencia"] <= 0).sum()),
            "duplicateKeys": int(valid.duplicated(["fecha", "linea", "estacion"]).sum()),
            "renamedStations": renamed,
            "nulls": nulls,
            "forecastStart": forecast_dates.min().strftime("%Y-%m-%d"),
            "forecastEnd": forecast_dates.max().strftime("%Y-%m-%d"),
            "forecastDays": FORECAST_DAYS,
        },
        "model": {
            "name": "Random Forest Regressor",
            "trees": RF_PARAMS["n_estimators"],
            "features": ["mes", "día de la semana", "día del mes", "fin de semana", "ciclo anual",
                         "días festivos", "fechas especiales", "puentes", "vacaciones de Semana Santa", "vacaciones de invierno"],
            "refit": "Tras validar, el modelo se reentrena con todos los datos válidos de su ventana antes de pronosticar.",
            "trainingWindow": f"Desde {TRAIN_START} si hay al menos {MIN_TRAIN_DAYS} días válidos; si no, todo el historial.",
            "recentWeight": f"Los últimos {RECENT_DAYS} días antes del corte pesan {RECENT_WEIGHT:g} veces más.",
            "validation": f"Partición cronológica por estación y línea: últimos {TEST_DAYS} días observados",
            "unit": "Un modelo por estación y línea, como publica el recurso oficial",
            "seed": RF_PARAMS["random_state"],
            "rules": {
                "zeroDays": "Los días con afluencia 0 (cierres) se excluyen del entrenamiento y la validación.",
                "minTrainDays": MIN_TRAIN_DAYS,
                "minTestDays": MIN_TEST_DAYS,
                "maxStaleDays": MAX_STALE_DAYS,
            },
        },
        "calendar": calendar_labels(forecast_dates),
        "featured": [{"line": line, "name": name} for line, name in FEATURED],
        "stations": records,
        "skipped": skipped,
    }

    output_path.write_text(
        "window.MINI_YOLOTZIN_DATA = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["dataset"], ensure_ascii=False, indent=2))
    print(f"Modelados: {len(records)} · Omitidos: {len(skipped)}")
    for item in skipped:
        print("  omitido:", item)
    gains = [(r["metrics"]["baselineMae"] - r["metrics"]["modelMae"]) / r["metrics"]["baselineMae"] for r in records if r["metrics"]["baselineMae"]]
    print(f"El modelo supera a la línea base en {sum(g > 0 for g in gains)} de {len(gains)} registros")


if __name__ == "__main__":
    main()
