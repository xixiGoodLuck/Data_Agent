from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

REAL_WORLD_MANIFEST_PATH = Path(__file__).with_name("real_world_manifest.json")

CHINA_COLUMNS = [
    "地区",
    "地区生产总值_亿元",
    "第一产业增加值_亿元",
    "第二产业增加值_亿元",
    "第三产业增加值_亿元",
    "人均地区生产总值_元",
    "地区生产总值指数_上年100",
    "总人口_万人",
    "城镇人口_万人",
    "城镇人口比重_百分比",
    "乡村人口_万人",
    "出生率_千分比",
    "死亡率_千分比",
    "自然增长率_千分比",
]

NOAA_COLUMN_MAP = {
    "STATION": "station",
    "DATE": "date",
    "TMAX": "tmax_c",
    "TMIN": "tmin_c",
    "PRCP": "precipitation_mm",
    "SNOW": "snowfall_mm",
    "SNWD": "snow_depth_mm",
    "AWND": "avg_wind_speed_ms",
    "WSF2": "max_2min_wind_speed_ms",
    "WT01": "fog",
    "WT02": "heavy_fog",
    "WT03": "thunder",
    "WT08": "smoke_haze",
}

WORLD_BANK_INDICATORS = {
    "SP.POP.TOTL": "population",
    "NY.GDP.MKTP.CD": "gdp_current_usd",
    "SP.DYN.LE00.IN": "life_expectancy_years",
}


def load_real_world_manifest(path: Path = REAL_WORLD_MANIFEST_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def csv_dimensions(path: Path) -> tuple[int, int]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(source)
        header = next(reader)
        return sum(1 for _ in reader), len(header)


def prepare_noaa_csv(source_path: Path, target_path: Path) -> None:
    with source_path.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    missing = set(NOAA_COLUMN_MAP) - set(rows[0] if rows else [])
    if missing:
        raise ValueError(f"NOAA source is missing columns: {sorted(missing)}")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=list(NOAA_COLUMN_MAP.values()))
        writer.writeheader()
        for row in rows:
            prepared: dict[str, Any] = {}
            for source_name, target_name in NOAA_COLUMN_MAP.items():
                value = (row.get(source_name) or "").strip()
                prepared[target_name] = int(bool(value)) if source_name.startswith("WT") else value
            writer.writerow(prepared)


def prepare_world_bank_csv(
    indicators_path: Path,
    countries_path: Path,
    target_path: Path,
) -> None:
    indicator_payload = json.loads(indicators_path.read_text(encoding="utf-8-sig"))
    country_payload = json.loads(countries_path.read_text(encoding="utf-8-sig"))
    raw_rows = indicator_payload[1]
    countries = country_payload[1]
    country_codes = {
        item["id"] for item in countries if item.get("region", {}).get("id") not in {None, "", "NA"}
    }
    pivot: dict[tuple[str, str, int], dict[str, Any]] = {}
    for item in raw_rows:
        iso3 = item.get("countryiso3code")
        indicator_id = item.get("indicator", {}).get("id")
        if iso3 not in country_codes or indicator_id not in WORLD_BANK_INDICATORS:
            continue
        key = (item["country"]["value"], iso3, int(item["date"]))
        pivot.setdefault(key, {})[WORLD_BANK_INDICATORS[indicator_id]] = item.get("value")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "country",
        "iso3",
        "year",
        "population",
        "gdp_current_usd",
        "life_expectancy_years",
    ]
    with target_path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        for key, values in sorted(pivot.items(), key=lambda pair: (pair[0][2], pair[0][1])):
            writer.writerow(dict(zip(fields[:3], key, strict=True)) | values)


def validate_china_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != CHINA_COLUMNS:
            raise ValueError("China CSV headers do not match the verified 14-column schema.")
        rows = list(reader)
    if len(rows) != 31:
        raise ValueError(f"China CSV must contain 31 provincial rows, found {len(rows)}.")
    regions = [row["地区"] for row in rows]
    if len(set(regions)) != len(regions):
        raise ValueError("China CSV contains duplicate region names.")
    for row in rows:
        region = row["地区"]
        numbers = {name: float(row[name]) for name in CHINA_COLUMNS[1:]}
        industry_sum = sum(
            numbers[name]
            for name in (
                "第一产业增加值_亿元",
                "第二产业增加值_亿元",
                "第三产业增加值_亿元",
            )
        )
        if abs(industry_sum - numbers["地区生产总值_亿元"]) > 0.25:
            raise ValueError(f"{region}: industry values do not reconcile with GDP.")
        if abs(numbers["城镇人口_万人"] + numbers["乡村人口_万人"] - numbers["总人口_万人"]) > 0.01:
            raise ValueError(f"{region}: urban and rural populations do not reconcile.")
        urban_share = numbers["城镇人口_万人"] * 100 / numbers["总人口_万人"]
        if abs(urban_share - numbers["城镇人口比重_百分比"]) > 0.15:
            raise ValueError(f"{region}: urban population share does not reconcile.")
        natural_growth = numbers["出生率_千分比"] - numbers["死亡率_千分比"]
        if abs(natural_growth - numbers["自然增长率_千分比"]) > 0.02:
            raise ValueError(f"{region}: natural growth rate does not reconcile.")
    return rows


def run_oracles(
    prepared_dir: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    datasets = {item["id"]: item for item in manifest["datasets"]}
    connections: dict[str, sqlite3.Connection] = {}
    try:
        for dataset_id, definition in datasets.items():
            frame = pd.read_csv(prepared_dir / definition["prepared_filename"])
            connection = sqlite3.connect(":memory:")
            frame.to_sql("data", connection, index=False, if_exists="replace")
            connections[dataset_id] = connection
        results: list[dict[str, Any]] = []
        for case in manifest["cases"]:
            result = {
                "id": case["id"],
                "dataset_id": case["dataset_id"],
                "language": case["language"],
                "question": case["question"],
                "expected_status": case["expected_status"],
                "expected_chart_type": case["expected_chart_type"],
                "oracle_sql": case["oracle_sql"],
                "columns": [],
                "rows": [],
            }
            if case["oracle_sql"]:
                cursor = connections[case["dataset_id"]].execute(case["oracle_sql"])
                result["columns"] = [item[0] for item in cursor.description]
                result["rows"] = [list(row) for row in cursor.fetchall()]
            results.append(result)
        return {"version": manifest["version"], "cases": results}
    finally:
        for connection in connections.values():
            connection.close()


def prepare_real_world_data(
    source_dir: Path,
    output_dir: Path,
    manifest_path: Path = REAL_WORLD_MANIFEST_PATH,
) -> dict[str, Any]:
    manifest = load_real_world_manifest(manifest_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    prepared_paths = {
        item["id"]: output_dir / item["prepared_filename"] for item in manifest["datasets"]
    }
    shutil.copyfile(
        source_dir / "usgs_all_month.csv",
        prepared_paths["usgs_earthquakes_30d"],
    )
    prepare_noaa_csv(
        source_dir / "noaa_jfk_2025.csv",
        prepared_paths["noaa_jfk_2025"],
    )
    prepare_world_bank_csv(
        source_dir / "world_bank_2015_2024.json",
        source_dir / "world_bank_countries.json",
        prepared_paths["world_bank_country_panel"],
    )
    china_source = source_dir / "china_nbs_2024.csv"
    validate_china_csv(china_source)
    shutil.copyfile(china_source, prepared_paths["china_nbs_provinces_2024"])

    snapshot = {
        "version": manifest["version"],
        "generated_at": datetime.now(UTC).isoformat(),
        "datasets": [],
    }
    for definition in manifest["datasets"]:
        source_files = []
        for filename in definition["source_filenames"]:
            path = source_dir / filename
            if not path.is_file():
                raise FileNotFoundError(path)
            source_files.append(
                {
                    "filename": filename,
                    "bytes": path.stat().st_size,
                    "sha256": file_sha256(path),
                }
            )
        prepared_path = prepared_paths[definition["id"]]
        rows, columns = csv_dimensions(prepared_path)
        snapshot["datasets"].append(
            {
                "id": definition["id"],
                "name": definition["name"],
                "source_urls": definition["source_urls"],
                "attribution": definition["attribution"],
                "source_files": source_files,
                "prepared_file": {
                    "filename": prepared_path.name,
                    "bytes": prepared_path.stat().st_size,
                    "sha256": file_sha256(prepared_path),
                    "rows": rows,
                    "columns": columns,
                },
            }
        )
    (output_dir / "real_world_snapshot.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    oracle = run_oracles(output_dir, manifest)
    (output_dir / "real_world_oracles.json").write_text(
        json.dumps(oracle, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare the InsightOps real-data benchmark.")
    parser.add_argument("--source-dir", type=Path, default=Path("C:/tmp"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("C:/tmp/insightops-real-eval"),
    )
    parser.add_argument(
        "--manifest-path",
        type=Path,
        default=REAL_WORLD_MANIFEST_PATH,
    )
    args = parser.parse_args()
    snapshot = prepare_real_world_data(
        args.source_dir,
        args.output_dir,
        args.manifest_path,
    )
    print(json.dumps(snapshot, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
