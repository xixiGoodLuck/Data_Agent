from app.charts.planner import plan_chart


def test_single_row_multi_metric_aggregate_uses_number() -> None:
    chart = plan_chart(
        "How many snow days and what was total snowfall?",
        ["snow_days", "total_snowfall_mm"],
        [{"snow_days": 13, "total_snowfall_mm": 454.0}],
    )

    assert chart.type == "number"
    assert chart.y_columns == ["snow_days", "total_snowfall_mm"]


def test_ranked_temporal_records_use_table() -> None:
    chart = plan_chart(
        "Find the 10 days with the highest average wind speed.",
        ["date", "avg_wind_speed_ms", "max_wind_speed_ms"],
        [
            {
                "date": "2025-01-09",
                "avg_wind_speed_ms": 11.4,
                "max_wind_speed_ms": 17.4,
            }
        ],
    )

    assert chart.type == "table"


def test_multi_dimension_event_records_use_table() -> None:
    chart = plan_chart(
        "Show the 10 strongest earthquakes.",
        ["time", "place", "magnitude", "depth"],
        [
            {
                "time": "2026-06-24T22:05:11Z",
                "place": "Example",
                "magnitude": 7.5,
                "depth": 10.0,
            }
        ],
    )

    assert chart.type == "table"


def test_multi_metric_ranked_rows_use_table() -> None:
    chart = plan_chart(
        "List the countries with the highest life expectancy.",
        ["country", "life_expectancy", "gdp", "population"],
        [
            {
                "country": "Example",
                "life_expectancy": 86.0,
                "gdp": 1_000_000,
                "population": 10_000,
            }
        ],
    )

    assert chart.type == "table"


def test_temporal_series_still_uses_line() -> None:
    chart = plan_chart(
        "Show the monthly temperature trend.",
        ["month", "avg_high", "avg_low"],
        [
            {"month": "2025-01", "avg_high": 3.9, "avg_low": -2.7},
            {"month": "2025-02", "avg_high": 6.6, "avg_low": -0.8},
        ],
    )

    assert chart.type == "line"


def test_chinese_monthly_high_low_temperature_is_not_mistaken_for_ranking() -> None:
    chart = plan_chart(
        "比较2025年各月平均最高气温和平均最低气温。",
        ["month", "avg_max_temp", "avg_min_temp"],
        [
            {"month": "2025-01", "avg_max_temp": 3.95, "avg_min_temp": -2.7},
            {"month": "2025-02", "avg_max_temp": 6.65, "avg_min_temp": -0.82},
        ],
    )

    assert chart.type == "line"


def test_chinese_hottest_day_is_ranked_temporal_output() -> None:
    chart = plan_chart(
        "2025年哪一天的最高气温最高?",
        ["date", "tmax_c"],
        [{"date": "2025-07-29", "tmax_c": 36.7}],
    )

    assert chart.type == "table"
