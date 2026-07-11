# 真实数据评测

状态：2026-07-11 真实 DeepSeek 预检、43 条内置回归、25 条中英混合开放数据用例及 25 条纯中文复测均已完成。一次性 Key 已清除；按用户要求，纯中文复测使用的四套数据仍保留在本地应用中。

## 方法

- 原始下载、规范化 CSV、快照清单和 oracle 输出只写入 `C:\tmp\insightops-real-eval`，不进入 Git。
- `backend/app/evals/real_world_manifest.json` 固定来源、问题、语言、预期状态、图表类型和独立 oracle SQL。
- `backend/app/evals/real_world_manifest.zh-CN.json` 使用相同数据与 oracle SQL 固定 25 条纯中文问题，便于与中英混合基准独立比较。
- `python -m app.evals.real_world --source-dir C:\tmp --output-dir C:\tmp\insightops-real-eval` 执行列裁剪、World Bank pivot、中国年鉴校验、SHA-256 和 oracle。
- 可通过 `--manifest-path app/evals/real_world_manifest.zh-CN.json` 为纯中文清单生成对应 oracle，不改变默认清单行为。
- 中国数据来自国家统计局《中国统计年鉴 2025》表 2-7 与 3-9。转录值逐行验证产业之和、城乡人口之和、城镇化率和人口自然增长率。
- 真实运行使用 `deepseek-v4-flash` 非思考模式和 2,048-token 输出上限；先做一条 USGS 预检，成功后再运行 43 条内置 case 与 25 条外部 case。
- DeepSeek 结构化输出显式使用 provider 支持的 function calling；不使用 LangChain 面向 OpenAI 的默认 `json_schema` 模式。

## 首次中英混合运行快照

| Dataset | Prepared shape | Prepared SHA-256 | Source |
| --- | ---: | --- | --- |
| USGS 近 30 天地震 | 10,522 × 22 | `e56f0c364e87c8810a0e9c6e1dc28532f666cd5979f0c9da750a6071e0ce3ca9` | [USGS CSV](https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_month.csv) |
| NOAA JFK 2025 日气象 | 365 × 13 | `d5e8a6cd260dd6742ac8b4d62a672d6d65faac1c50e75040d814613f195e16ee` | [NOAA NCEI](https://www.ncei.noaa.gov/access/services/data/v1?dataset=daily-summaries&stations=USW00094789&startDate=2025-01-01&endDate=2025-12-31&format=csv&units=metric&includeAttributes=false) |
| World Bank 2015–2024 | 2,170 × 6 | `2748dfeee96363db9cff1646b83af5acf6b26ee4a4f82b47699fa02403ce05de` | [Indicators API](https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL%3BNY.GDP.MKTP.CD%3BSP.DYN.LE00.IN?source=2&date=2015%3A2024&format=json&per_page=20000) |
| 国家统计局 2024 省级经济人口 | 31 × 14 | `7fa064b9b6a01f1a4031436db9e1da8eab8533f21af56b26c6de6f7c2a60474e` | [人口表 2-7](https://www.stats.gov.cn/sj/ndsj/2025/html/C02-07.jpg)、[GDP 表 3-9](https://www.stats.gov.cn/sj/ndsj/2025/html/C03-09.jpg) |

NOAA 原始文件为 151 列，准备步骤只保留温度、降水、积雪、风速和天气标志 13 列。World Bank 数据通过国家元数据排除 `region.id=NA` 的区域和收入组汇总，再按 country-year pivot；82 个真实 GDP 缺失值保持为空。

## 纯中文复测快照

纯中文复测在 `2026-07-11T08:16:44Z` 重新取得官方源；USGS 实时窗口因此与首次运行不同，其余三个准备文件哈希保持一致。

| Dataset | Prepared shape | Prepared SHA-256 |
| --- | ---: | --- |
| USGS 近 30 天地震 | 10,492 × 22 | `7d49fb35fb7f7fdb8db81f38154ece7297c5566bd35e812462ce33bfd83d6f51` |
| NOAA JFK 2025 日气象 | 365 × 13 | `d5e8a6cd260dd6742ac8b4d62a672d6d65faac1c50e75040d814613f195e16ee` |
| World Bank 2015–2024 | 2,170 × 6 | `2748dfeee96363db9cff1646b83af5acf6b26ee4a4f82b47699fa02403ce05de` |
| 国家统计局 2024 省级经济人口 | 31 × 14 | `7fa064b9b6a01f1a4031436db9e1da8eab8533f21af56b26c6de6f7c2a60474e` |

## 用例与判定

- USGS、NOAA、World Bank 各 5 条分析问题，国家统计局 6 条分析问题；中英文混合。
- 纯中文复测保持相同的 21 条分析意图、4 条攻击和全部 oracle SQL，仅将问题统一为 `zh-CN`。
- 每个数据集另有 1 条 DROP、ATTACH、PRAGMA 或 DELETE 攻击，总计 4 条安全用例。
- 成功查询按 oracle 的有序 rows 比较，浮点值使用明确容差；安全用例要求在执行前返回 `blocked`。
- 报告记录 generated SQL、status、chart、fallback、latency、oracle 差异和失败原因。

质量目标：SQL 安全拦截 100%，Key 泄漏为 0，真实模型 fallback 为 0，结果准确率至少 80%，图表选择至少 80%。未达标结果会原样报告，不用 Mock 结果替代。

## Key 交接与清理

1. 启动 `8002/5175` 后打开 `/settings`。
2. 用户亲自在一次性输入框中粘贴 Key，只回复“已填好”；不要把 Key 发到聊天或终端。
3. 自动化不读取、不截图该输入框。Eval 和 Ask Data 请求通过 `X-DeepSeek-API-Key` 使用页面内存值。
4. 完成或失败后刷新/关闭页面，确认状态恢复“未设置”。上传数据和 `C:\tmp` 快照是否删除由本次交付要求决定，二者都不得进入 Git。

## 真实运行结果

USGS 预检返回 provider=`deepseek`、fallback=`false`、chart=`number`，结果 `535` 与独立 oracle 一致。预检后才启动批量调用。

### 43 条内置回归

- 35/43 通过；结果准确率、选表准确率和 SQL 安全准确率均为 100%。
- 危险 SQL 拦截率 100%，图表选择准确率 81.48%，fallback 0%。
- 8 条失败：2 条澄清策略、5 条图表类型、1 条预设 repair 未触发。
- [逐条内置回归报告](deepseek-builtin-evaluation-results.md)

### 25 条开放数据用例

- 16/25 全指标通过；19 条分析返回 success，4 条攻击全部 blocked，1 条误触发 pending approval，1 条要求 clarification。
- 真实数据结果准确率 80.95%，达到至少 80% 的目标。
- 图表选择准确率 66.67%，未达到至少 80% 的目标。
- SQL 安全拦截率 100%，DeepSeek provider 100%，fallback 0%，平均耗时 6,685.50 ms。
- 中国专项 6 条分析中 5 条结果与图表均正确；中英混合出生率用例因表内没有显式年份列而要求澄清。中国 `DELETE` 攻击被 SQL Safety Gate 拦截。
- [逐条开放数据报告](real-data-evaluation-results.md)

### 25 条纯中文复测

- 14/25 全指标通过；20 条分析返回 `success`，4 条攻击全部 `blocked`，1 条中国人口变化查询误触发 `pending_approval`。
- 真实数据结果准确率 66.67%，图表选择准确率 71.43%，均未达到至少 80% 的目标。
- SQL 安全拦截率 100%，DeepSeek provider 100%，fallback 0%，平均耗时 6,524.67 ms。
- 中国专项 6 条分析全部完成中文表头解析，其中 5 条结果与 oracle 一致；出生率用例返回了额外地区。中国 `DELETE` 攻击由 SQL Safety Gate 拦截。
- USGS 预检返回 `533`，与该次实时快照 oracle 一致；批量调用仅在预检通过后启动。
- [逐条纯中文报告](real-data-evaluation-results.zh-CN.md)

### 修复与清理

- 首次网络错误来自受限进程；切换为获准联网的本地后端后恢复。
- 首次 400 来自 LangChain 默认 `json_schema` 与 DeepSeek 不兼容；固定为 function calling 后预检通过。
- 中国列别名最初只进入 SQL schema context，选表 catalog 仍只有 `column_*`；补齐 JSON 转义别名后，前三条中国用例由 clarification 变为 success。
- 页面刷新后一次性 Key 状态恢复“未设置”。通用真实 Key 模式扫描在仓库、runtime 和脱敏报告中为 0 命中。
- 首次中英混合运行结束后，四个上传数据集及 `C:\tmp` 快照已删除。纯中文复测重新导入四套数据并按用户要求保留在本地应用；原始文件和准备快照仍只位于 `C:\tmp`，仓库只保留来源、哈希、规范和脱敏报告。
