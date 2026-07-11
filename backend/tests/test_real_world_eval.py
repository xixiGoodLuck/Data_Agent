from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from app.evals.real_world import (
    CHINA_COLUMNS,
    load_real_world_manifest,
    prepare_noaa_csv,
    prepare_world_bank_csv,
    validate_china_csv,
)
from app.evals.real_world_report import assess_case, compare_rows


def test_real_world_manifest_has_four_datasets_and_twenty_five_cases() -> None:
    manifest = load_real_world_manifest()

    assert len(manifest["datasets"]) == 4
    assert len(manifest["cases"]) == 25
    assert sum(case["expected_status"] == "blocked" for case in manifest["cases"]) == 4
    assert {case["language"] for case in manifest["cases"]} == {"en", "zh-CN"}


def test_prepare_noaa_csv_selects_and_renames_safe_columns(tmp_path: Path) -> None:
    source = tmp_path / "noaa.csv"
    source.write_text(
        "STATION,DATE,TMAX,TMIN,PRCP,SNOW,SNWD,AWND,WSF2,WT01,WT02,WT03,WT08,EXTRA\n"
        "JFK,2025-01-01,11.7,5.0,0.0,0.0,0.0,7.3,14.8,    1,,,,ignored\n",
        encoding="utf-8",
    )
    target = tmp_path / "prepared.csv"

    prepare_noaa_csv(source, target)

    with target.open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["station"] == "JFK"
    assert row["tmax_c"] == "11.7"
    assert row["fog"] == "1"
    assert "EXTRA" not in row


def test_prepare_world_bank_csv_excludes_aggregate_regions(tmp_path: Path) -> None:
    indicators = tmp_path / "indicators.json"
    countries = tmp_path / "countries.json"
    indicators.write_text(
        json.dumps(
            [
                {"total": 2},
                [
                    {
                        "indicator": {"id": "SP.POP.TOTL"},
                        "country": {"value": "China"},
                        "countryiso3code": "CHN",
                        "date": "2024",
                        "value": 10,
                    },
                    {
                        "indicator": {"id": "SP.POP.TOTL"},
                        "country": {"value": "World"},
                        "countryiso3code": "WLD",
                        "date": "2024",
                        "value": 20,
                    },
                ],
            ]
        ),
        encoding="utf-8",
    )
    countries.write_text(
        json.dumps(
            [
                {"total": 2},
                [
                    {"id": "CHN", "region": {"id": "EAS"}},
                    {"id": "WLD", "region": {"id": "NA"}},
                ],
            ]
        ),
        encoding="utf-8",
    )
    target = tmp_path / "world-bank.csv"

    prepare_world_bank_csv(indicators, countries, target)

    rows = list(csv.DictReader(target.open(encoding="utf-8", newline="")))
    assert len(rows) == 1
    assert rows[0]["iso3"] == "CHN"


def test_validate_china_csv_checks_cross_table_invariants(tmp_path: Path) -> None:
    path = tmp_path / "china.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CHINA_COLUMNS)
        writer.writeheader()
        for index in range(31):
            writer.writerow(
                {
                    "地区": f"地区{index}",
                    "地区生产总值_亿元": 100,
                    "第一产业增加值_亿元": 10,
                    "第二产业增加值_亿元": 40,
                    "第三产业增加值_亿元": 50,
                    "人均地区生产总值_元": 100000,
                    "地区生产总值指数_上年100": 105,
                    "总人口_万人": 100,
                    "城镇人口_万人": 60,
                    "城镇人口比重_百分比": 60,
                    "乡村人口_万人": 40,
                    "出生率_千分比": 8,
                    "死亡率_千分比": 7,
                    "自然增长率_千分比": 1,
                }
            )

    assert len(validate_china_csv(path)) == 31

    content = path.read_text(encoding="utf-8").replace(",40,8,7,1\n", ",41,8,7,1\n", 1)
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match="populations do not reconcile"):
        validate_china_csv(path)


def test_real_world_row_comparison_uses_order_and_numeric_tolerance() -> None:
    assert compare_rows([["A", 1.0]], [["A", 1.019]])
    assert not compare_rows([["A", 1.0]], [["A", 1.021]])
    assert not compare_rows([["A"], ["B"]], [["B"], ["A"]])


def test_real_world_case_assessment_separates_rows_and_chart() -> None:
    oracle = {
        "id": "sample",
        "dataset_id": "dataset",
        "language": "en",
        "question": "Question",
        "expected_status": "success",
        "expected_chart_type": "bar",
        "columns": ["name", "value"],
        "rows": [["A", 1]],
    }
    detail = {
        "id": "log",
        "status": "success",
        "generated_sql": "SELECT name, value FROM data",
        "normalized_sql": "SELECT name, value FROM data LIMIT 100",
        "chart_type": "table",
        "llm_provider": "deepseek",
        "used_fallback": False,
        "execution_time_ms": 12.3,
        "result": {"columns": ["name", "value"], "rows": [{"name": "A", "value": 1}]},
    }

    assessed = assess_case(oracle, detail)

    assert assessed["result_ok"] is True
    assert assessed["chart_ok"] is False
    assert assessed["failure_reasons"] == ["chart"]
