"""Build the compact browser dataset used by the Mini Yolotzin demo.

The raw CSV is an input artifact and is intentionally not shipped with the site.
The output contains only aggregate history, validation metrics and precomputed
future estimates for the five selected stations.
"""

from __future__ import annotations

import json
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
SELECTED_LINE = "Línea 3"
SELECTED_STATIONS = [
    "Indios Verdes",
    "La Raza",
    "Hidalgo",
    "Centro Médico",
    "Universidad",
]


def repair_mojibake(value: object) -> object:
    if not isinstance(value, str) or "Ã" not in value:
        return value
    try:
        return value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def features(dates: pd.Series | pd.DatetimeIndex) -> pd.DataFrame:
    dates = pd.DatetimeIndex(dates)
    day_of_year = dates.dayofyear.to_numpy()
    return pd.DataFrame(
        {
            "month": dates.month,
            "dow": dates.dayofweek,
            "day": dates.day,
            "weekend": (dates.dayofweek >= 5).astype(int),
            "sin_year": np.sin(2 * np.pi * day_of_year / 365.25),
            "cos_year": np.cos(2 * np.pi * day_of_year / 365.25),
        }
    )


def rounded(value: float) -> int:
    return int(round(float(value)))


def build_station(station: str, frame: pd.DataFrame, forecast_dates: pd.DatetimeIndex) -> dict:
    data = frame.loc[frame["estacion"] == station, ["fecha", "afluencia"]].copy()
    data = data.sort_values("fecha").drop_duplicates("fecha", keep="last")

    cutoff = data["fecha"].max() - pd.DateOffset(days=179)
    train = data[data["fecha"] < cutoff].copy()
    test = data[data["fecha"] >= cutoff].copy()

    baseline_table = train.assign(
        month=train["fecha"].dt.month,
        dow=train["fecha"].dt.dayofweek,
    ).groupby(["month", "dow"])["afluencia"].mean()
    station_mean = float(train["afluencia"].mean())
    baseline_pred = [
        baseline_table.get((date.month, date.dayofweek), station_mean)
        for date in test["fecha"]
    ]

    model = RandomForestRegressor(
        n_estimators=160,
        max_depth=14,
        min_samples_leaf=4,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(features(train["fecha"]), train["afluencia"])
    model_pred = model.predict(features(test["fecha"]))
    future_pred = np.maximum(0, model.predict(features(forecast_dates)))

    q33, q67 = train["afluencia"].quantile([0.33, 0.67]).tolist()
    q25, median, q75 = train["afluencia"].quantile([0.25, 0.5, 0.75]).tolist()
    recent_start = data["fecha"].max() - pd.DateOffset(months=17)
    recent = (
        data[data["fecha"] >= recent_start]
        .set_index("fecha")["afluencia"]
        .resample("MS")
        .mean()
        .dropna()
    )

    predictions = {}
    for date, prediction in zip(forecast_dates, future_pred):
        level = "baja" if prediction < q33 else "media" if prediction < q67 else "alta"
        predictions[date.strftime("%Y-%m-%d")] = {"value": rounded(prediction), "level": level}

    return {
        "name": station,
        "summary": {
            "mean": rounded(train["afluencia"].mean()),
            "median": rounded(median),
            "p25": rounded(q25),
            "p75": rounded(q75),
            "lowThreshold": rounded(q33),
            "highThreshold": rounded(q67),
            "observations": int(len(data)),
        },
        "metrics": {
            "baselineMae": rounded(mean_absolute_error(test["afluencia"], baseline_pred)),
            "baselineRmse": rounded(root_mean_squared_error(test["afluencia"], baseline_pred)),
            "modelMae": rounded(mean_absolute_error(test["afluencia"], model_pred)),
            "modelRmse": rounded(root_mean_squared_error(test["afluencia"], model_pred)),
            "testStart": test["fecha"].min().strftime("%Y-%m-%d"),
            "testEnd": test["fecha"].max().strftime("%Y-%m-%d"),
        },
        "history": [
            {"month": date.strftime("%Y-%m"), "value": rounded(value)}
            for date, value in recent.items()
        ],
        "predictions": predictions,
    }


def main() -> None:
    frame = pd.read_csv(CSV_PATH, dtype={"linea": "string", "estacion": "string"})
    for column in ["mes", "linea", "estacion"]:
        frame[column] = frame[column].map(repair_mojibake)
    # The official resource changed labels from “Línea 3” to “Linea 3” on
    # 2023-06-01. Normalize that schema drift before filtering or counting.
    frame["linea"] = frame["linea"].str.replace(r"^Linea ", "Línea ", regex=True)
    frame["fecha"] = pd.to_datetime(frame["fecha"], errors="coerce")
    frame["afluencia"] = pd.to_numeric(frame["afluencia"], errors="coerce")

    nulls = {key: int(value) for key, value in frame.isna().sum().items()}
    valid = frame.dropna(subset=["fecha", "linea", "estacion", "afluencia"]).copy()
    selected = valid[(valid["linea"] == SELECTED_LINE) & valid["estacion"].isin(SELECTED_STATIONS)]
    missing = sorted(set(SELECTED_STATIONS) - set(selected["estacion"].unique()))
    if missing:
        raise RuntimeError(f"Selected stations absent from the official CSV: {missing}")

    max_date = valid["fecha"].max()
    forecast_dates = pd.date_range(max_date + pd.DateOffset(days=1), periods=366, freq="D")
    stations = [build_station(name, selected, forecast_dates) for name in SELECTED_STATIONS]

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
            "duplicateKeys": int(valid.duplicated(["fecha", "linea", "estacion"]).sum()),
            "nulls": nulls,
            "selectedLine": SELECTED_LINE,
            "selectedRows": int(len(selected)),
            "forecastStart": forecast_dates.min().strftime("%Y-%m-%d"),
            "forecastEnd": forecast_dates.max().strftime("%Y-%m-%d"),
        },
        "model": {
            "name": "Random Forest Regressor",
            "trees": 160,
            "features": ["mes", "día de la semana", "día del mes", "fin de semana", "ciclo anual"],
            "validation": "Partición cronológica: últimos 180 días observados",
            "seed": 42,
        },
        "stations": stations,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        "window.MINI_YOLOTZIN_DATA = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["dataset"], ensure_ascii=False, indent=2))
    print("metrics")
    for station in stations:
        print(station["name"], station["metrics"])


if __name__ == "__main__":
    main()
