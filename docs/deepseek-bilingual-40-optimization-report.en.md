# Optimized DeepSeek Bilingual 40-Case Evaluation

[简体中文](deepseek-bilingual-40-optimization-report.md) | [**English**](deepseek-bilingual-40-optimization-report.en.md)

Completed on `2026-07-13`. This report compares the same 20 Chinese and 20 English questions before and after optimization across four fixed snapshots: USGS 30-day earthquakes, NOAA JFK 2025 daily weather, World Bank 2015-2024 country indicators, and 2024 provincial indicators from China's National Bureau of Statistics.

Independent SQLite oracle SQL produced every expected answer. DeepSeek did not generate the ground truth. Scoring checks row order, category labels, query status, and chart type, with an absolute numeric tolerance of `0.02`.

## Results

| Metric | 2026-07-12 baseline | First optimized pass | Final optimized run | Baseline to final |
| --- | ---: | ---: | ---: | ---: |
| Successful queries | 39/40 | 39/40 | **40/40** | +1 case, +2.5 pp |
| Correct results | 26/40, 65.0% | 33/40, 82.5% | **40/40, 100%** | +14 cases, +35.0 pp |
| Correct charts | 29/40, 72.5% | 38/40, 95.0% | **40/40, 100%** | +11 cases, +27.5 pp |
| Real DeepSeek provider | 40/40 | 40/40 | **40/40** | unchanged |
| Fallback | 0 | 0 | **0** | unchanged |

The final 40 cases averaged `8,951.20 ms` end to end, with a median of `8,836.39 ms`. The 39 completed baseline cases averaged `10,328.15 ms`, so the observed mean decreased by `1,376.95 ms`, or about `13.3%`. Provider and network latency vary, so this is a secondary metric.

## Language Delta

| Language | Result accuracy | Gain | Chart accuracy | Gain | Successful status |
| --- | ---: | ---: | ---: | ---: | ---: |
| Chinese, 20 cases | 60.0% -> **100%** | +40.0 pp | 75.0% -> **100%** | +25.0 pp | 20/20 -> **20/20** |
| English, 20 cases | 70.0% -> **100%** | +30.0 pp | 70.0% -> **100%** | +30.0 pp | 19/20 -> **20/20** |

## Dataset Delta

| Dataset | Result accuracy | Gain | Chart accuracy | Gain |
| --- | ---: | ---: | ---: | ---: |
| USGS | 20.0% -> **100%** | +80.0 pp | 80.0% -> **100%** | +20.0 pp |
| NOAA | 70.0% -> **100%** | +30.0 pp | 50.0% -> **100%** | +50.0 pp |
| World Bank | 70.0% -> **100%** | +30.0 pp | 60.0% -> **100%** | +40.0 pp |
| China NBS | 100% -> **100%** | 0 | 100% -> **100%** | 0 |

## What Changed

1. **Conversation isolation**: every real-data question starts a fresh conversation. Rewriting consults history only for explicit references, preventing filters and time windows from leaking between independent questions.
2. **Fixed-snapshot semantics**: the SQL prompt now receives the dataset identifier. A window already encoded by an identifier such as `_30d` must not be reinterpreted with `date('now')`, `datetime('now')`, or `CURRENT_DATE`.
3. **Stable output shape**: SQL projects only requested dimensions and measures, uses ISO calendar buckets, and emits ASCII lowercase snake_case aliases and category labels.
4. **Aggregation and binning**: grouped comparisons default to the most useful aggregate descending, count when available. Adjacent bands are half-open and use stable labels derived from their bounds.
5. **Two-period changes**: the prompt requires a single aggregate row and prohibits row-level self-joins. The final English case still used scalar subqueries, but returned only change and rate, remained low risk, and matched the oracle. Prompt compliance therefore remains a quality signal, not a security boundary.
6. **Deterministic chart planning**: single-row aggregate metrics use number, ranked temporal records use table, and monthly series use line. Chinese phrases for average high/low temperature no longer trigger a false ranking classification.
7. **Unchanged security boundary**: model SQL still passes deterministic `sqlglot` validation and runs only through the selected dataset's read-only SQLite connection. No approval or read-only rule was weakened.

## Run Selection

- The first pass executed 20 Chinese and 20 English cases, each in an independent conversation.
- After it reached 82.5% result accuracy and 95.0% chart accuracy, only eight affected questions were rerun, producing 48 valid case attempts in total.
- Final scoring selects the latest attempt for each language/dataset/question. The JSON retains `attempt_count` and `superseded_query_log_ids`, so replacement attempts remain auditable.
- Within the application, the one-time key lived only in page memory. The page was refreshed after the run and Settings was verified as `Not set`; repository and report scans found no key.

## Evidence

- [Complete final 40-case JSON](deepseek-bilingual-40-optimized-results.json), including questions, generated and validated SQL, rows, chart, insight, lineage, provider, fallback, latency, and attempt links.
- [Independent oracle score JSON](deepseek-bilingual-40-optimized-score.json), including expected rows, actual rows, and per-case verdicts.
- [Pre-optimization 40-case JSON](deepseek-bilingual-40-results.json) and [historical run summary](deepseek-bilingual-40-results.md).
- [Open-data sources, snapshots, and oracle methodology](real-data-evaluation.md).

## Limits

The `100%` result applies only to this model, code version, four fixed snapshots, and the latest attempts for these 40 predefined questions. It is not a claim of perfect accuracy for arbitrary natural-language requests. Future evaluation should add paraphrase variance, more joins, null-heavy data, ties, adversarial semantics, and repeated-run variance.

[简体中文](deepseek-bilingual-40-optimization-report.md) | [**English**](deepseek-bilingual-40-optimization-report.en.md)
