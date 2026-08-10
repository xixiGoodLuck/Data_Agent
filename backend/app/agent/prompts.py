from langchain_core.prompts import ChatPromptTemplate

REWRITE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Rewrite the latest analytics question as a self-contained request. If it is already "
            "self-contained, preserve it verbatim and set used_history=false. Use recent history only "
            "to resolve explicit references such as pronouns or phrases like 'same group'; never copy "
            "prior filters, time windows, rankings, tables, or metrics into an independent question. "
            "Never add facts not present in the latest question or required to resolve a reference."
            " Return the rewritten question in the language specified by response_language: use "
            "Simplified Chinese for zh-CN and English for en.",
        ),
        (
            "human",
            "Response language: {response_language}\nHistory:\n{history}\n\n"
            "Latest question:\n{question}",
        ),
    ]
)

ANALYSIS_INTENT_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Classify the user's analytical intent. Mark needs_multi_step=false for a direct "
            "lookup, comparison, ranking, or trend that one grouped query can answer. Mark it true "
            "only for diagnostic or exploratory work that requires evidence from one result to "
            "choose the next question. A bounded period comparison that decomposes one metric into "
            "explicitly "
            "named factors remains a direct comparison when one query can calculate every factor. "
            "A request to decide which of explicitly named components contributed more MUST be "
            "classified as comparison, not diagnostic, unless it also asks to discover additional "
            "unknown drivers. "
            "Likewise, listing grouped metrics and selecting the group with a requested high/low "
            "combination remains a direct comparison or ranking; multiple aggregates alone do not "
            "make a request exploratory. Keep reason brief and auditable; do not reveal hidden "
            "reasoning. Extract only explicit metrics, dimensions, filters, time range, comparison, "
            "and desired grain. All user-facing natural-language fields must be Simplified Chinese "
            "when response_language is zh-CN and English when it is en.",
        ),
        ("human", "Response language: {response_language}\nQuestion: {question}"),
    ]
)

ANALYSIS_PLAN_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Create a bounded analysis plan containing analytical questions only. Never output SQL, "
            "SQL fragments, tool calls, or database commands. Start by verifying the reported "
            "phenomenon, then decompose the core metric, and let later directions depend on evidence "
            "from earlier steps. Do not mechanically enumerate every available dimension. Return no "
            "more than {max_steps} steps. All user-facing natural-language fields must be Simplified "
            "Chinese when response_language is zh-CN and English when it is en.",
        ),
        (
            "human",
            "Response language: {response_language}\nObjective: {objective}\n"
            "Analysis type: {analysis_type}\nMetrics: {metrics}\n"
            "Dimensions: {dimensions}\nOriginal question: {question}",
        ),
    ]
)

ANALYSIS_EVALUATION_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Evaluate the structured evidence against the original objective and return a critic "
            "plus one next decision. Use only evidence summaries, deterministic key values, lineage, "
            "and limitations. Continue only when a specific evidence gap can be addressed by one "
            "analytical question. The next step must be dynamically chosen from observed evidence, "
            "not copied mechanically from the initial plan. Finish when the objective is answered or "
            "the reported phenomenon is disproved. Clarify only when safe continuation requires a "
            "missing user definition. Never output SQL or hidden reasoning; keep reasons brief and "
            "auditable. All user-facing natural-language fields must be Simplified Chinese when "
            "response_language is zh-CN and English when it is en.",
        ),
        (
            "human",
            "Response language: {response_language}\nObjective: {objective}\n"
            "Current plan: {plan}\nEvidence summaries: {evidence}\n"
            "Completed steps: {step_count}\nMaximum steps: {max_steps}",
        ),
    ]
)

FINAL_ANALYSIS_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Produce a concise final analysis using only the supplied structured evidence. Every "
            "finding must cite existing evidence IDs. Put numeric claims in both the statement and "
            "facts using the exact key and value from cited evidence. Never invent causes, numbers, "
            "external factors, or hidden reasoning. Treat recommended actions as proposals, not as "
            "verified facts. Put citations only in evidence_ids, not as numbers in statement text. "
            "Preserve evidence_insufficient when it is true. All user-facing natural-language fields "
            "must be Simplified Chinese when response_language is zh-CN and English when it is en.",
        ),
        (
            "human",
            "Response language: {response_language}\nOriginal question: {question}\n"
            "Intent: {intent}\nFinal plan: {plan}\n"
            "Evidence: {evidence}\nCritic: {critic}\n"
            "Evidence insufficient: {evidence_insufficient}",
        ),
    ]
)

TABLE_SELECTION_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Select the minimum relevant dataset tables from the lightweight catalog. Return a "
            "clarification only when the request cannot be mapped safely. Treat metrics that can "
            "be derived from available columns as mapped (for example, revenue divided by orders "
            "for average order value); do not require a precomputed column. For an investigation "
            "step that names unavailable optional dimensions, use the available time, metric, and "
            "breakdown columns when they can still answer the core question; do not request "
            "clarification solely because an optional example dimension is absent. User-facing reasons and "
            "clarifications must be Simplified Chinese when response_language is zh-CN and English "
            "when it is en.",
        ),
        (
            "human",
            "Response language: {response_language}\nQuestion: {question}\n"
            "Available tables: {table_catalog}",
        ),
    ]
)

SQL_GENERATION_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Generate one SQLite SELECT query using only the supplied schema. Do not add comments, "
            "database qualifiers, PRAGMA statements, or write operations. Use explicit joins. For "
            "SQLite, do not use MEDIAN, PERCENTILE_CONT, STDDEV, STDEV, or other functions absent from "
            "SQLite's built-in function set; omit unrequested distribution statistics instead. For "
            "investigative metric analysis, prefer a bounded aggregate grouped by the relevant time "
            "or business dimensions instead of returning broad row-level data. Treat "
            "a time window or year embedded in the dataset identifier as the scope of a fixed snapshot: "
            "query the full snapshot unless the question explicitly requests a narrower interval, and "
            "never reinterpret it with SQLite now/current-date functions. When the question repeats the "
            "same window already encoded in the dataset identifier (for example, 'past 30 days' for a "
            "dataset ending in _30d), do not add a time predicate. Never use date('now'), "
            "datetime('now'), CURRENT_DATE, CURRENT_TIME, or CURRENT_TIMESTAMP for a fixed snapshot. "
            "For latest or recent periods in a fixed snapshot, derive the maximum stored date or "
            "period inside the query and select periods relative to that maximum. Never invent or "
            "hardcode a calendar date that the user did not provide. "
            "Do not infer filters from "
            "earlier questions or from examples. Project only the dimensions and measures requested; "
            "do not return filter constants or intermediate operands. For a ranked record, include both "
            "the identifying dimension and the ranked measure. Format calendar buckets as ISO YYYY-MM "
            "or YYYY-MM-DD. Use ASCII lowercase English snake_case aliases and category labels regardless "
            "of the question language. Define adjacent numeric bands as half-open [lower, upper) "
            "intervals and label them from their bounds, such as under_10_km, 10_50_km, and "
            "100_km_or_more. Respect the business grain of every metric: compute a parent-entity metric "
            "at the parent grain before an outer aggregate. For example, average order value over line "
            "items requires summing line values per order and then averaging those order totals; never "
            "label an average detail-row value as an average parent value. Prevent join fanout when two "
            "or more one-to-many children share a parent: aggregate each child to the parent key before "
            "joining. Do not duplicate a parent-level measure across child rows; when a parent measure "
            "must be attributed to a child dimension, use an explicit deterministic allocation whose "
            "allocated totals reconcile to the parent total. Carry the requested dimension key through "
            "the allocation rows and aggregate those rows directly; never join allocated child rows "
            "back to the original child table on a non-unique business key. For a grouped comparison "
            "with no requested "
            "order, sort by the most useful "
            "aggregate descending; prefer the count when one is present. Period-to-period changes MUST "
            "use conditional aggregation in one aggregate row. Do not self-join or use scalar/correlated "
            "subqueries for such changes, and return only the requested change and rate.",
        ),
        (
            "human",
            "Dataset identifier: {dataset_id}\nQuestion: {question}\nSchema:\n{schema_context}",
        ),
    ]
)

SQL_REPAIR_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Repair the SQLite SELECT using only the supplied schema and sanitized error category. "
            "Return one read-only query without comments. Preserve the requested output shape and the "
            "fixed-snapshot semantics, business grain, and fanout-safe aggregation rules from the "
            "generation contract. Remove MEDIAN, PERCENTILE_CONT, STDDEV, STDEV, and other functions "
            "that are not built into SQLite. When grouping by a dimension from one child table and "
            "aggregating a parent-level measure derived from a sibling child, allocate that parent "
            "measure proportionally using the requested child's share within each parent; joining the "
            "parent total to every child row or distinct child group still duplicates it and is not "
            "a valid repair. Preaggregating only the parent-level measure does not make that repeated "
            "join safe, and a repaired query must contain the explicit allocation. When averaging a "
            "parent entity value derived from child rows, first sum the child values by parent key, "
            "then average those parent totals by the requested dimension; SUM(child_value) divided "
            "by COUNT(DISTINCT parent_id) is not a valid repair for this contract. "
            "Use this generic allocation pattern when needed: compute child_measure and "
            "SUM(child_measure) OVER (PARTITION BY parent_id) as parent_child_total, preaggregate the "
            "sibling_measure by parent_id, calculate sibling_total * child_measure / "
            "NULLIF(parent_child_total, 0), and only then aggregate that allocated measure by the child "
            "dimension. Carry the dimension key in those allocation rows and aggregate them directly; "
            "do not join them back to the original child table on parent_id plus a potentially repeated "
            "dimension key. For aggregate_fanout specifically, the repair is valid only when the "
            "parent or sibling measure is multiplied by child_measure / NULLIF(parent_child_total, 0) "
            "before the outer dimension grouping. Do not return the original join with only one child "
            "preaggregated.",
        ),
        (
            "human",
            "Dataset identifier: {dataset_id}\nQuestion: {question}\nSchema:\n{schema_context}\n"
            "SQL: {sql}\nError: {error_type}",
        ),
    ]
)

INSIGHT_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Write a concise grounded insight using only the question, validated SQL, columns, and "
            "rows. Separate observation from cautious interpretation and state causal limitations. "
            "Write all natural language in Simplified Chinese when response_language is zh-CN and "
            "English when it is en. Do not translate SQL identifiers.",
        ),
        (
            "human",
            "Response language: {response_language}\nQuestion: {question}\nSQL: {sql}\n"
            "Columns: {columns}\nRows: {rows}",
        ),
    ]
)
