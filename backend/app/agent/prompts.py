from langchain_core.prompts import ChatPromptTemplate

REWRITE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Rewrite the latest analytics question as a self-contained request. If it is already "
            "self-contained, preserve it verbatim and set used_history=false. Use recent history only "
            "to resolve explicit references such as pronouns or phrases like 'same group'; never copy "
            "prior filters, time windows, rankings, tables, or metrics into an independent question. "
            "Never add facts not present in the latest question or required to resolve a reference.",
        ),
        ("human", "History:\n{history}\n\nLatest question:\n{question}"),
    ]
)

TABLE_SELECTION_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Select the minimum relevant dataset tables from the lightweight catalog. Return a "
            "clarification when the request cannot be mapped safely.",
        ),
        ("human", "Question: {question}\nAvailable tables: {table_catalog}"),
    ]
)

SQL_GENERATION_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Generate one SQLite SELECT query using only the supplied schema. Do not add comments, "
            "database qualifiers, PRAGMA statements, or write operations. Use explicit joins. Treat "
            "a time window or year embedded in the dataset identifier as the scope of a fixed snapshot: "
            "query the full snapshot unless the question explicitly requests a narrower interval, and "
            "never reinterpret it with SQLite now/current-date functions. When the question repeats the "
            "same window already encoded in the dataset identifier (for example, 'past 30 days' for a "
            "dataset ending in _30d), do not add a time predicate. Never use date('now'), "
            "datetime('now'), CURRENT_DATE, CURRENT_TIME, or CURRENT_TIMESTAMP for a fixed snapshot. "
            "Do not infer filters from "
            "earlier questions or from examples. Project only the dimensions and measures requested; "
            "do not return filter constants or intermediate operands. For a ranked record, include both "
            "the identifying dimension and the ranked measure. Format calendar buckets as ISO YYYY-MM "
            "or YYYY-MM-DD. Use ASCII lowercase English snake_case aliases and category labels regardless "
            "of the question language. Define adjacent numeric bands as half-open [lower, upper) "
            "intervals and label them from their bounds, such as under_10_km, 10_50_km, and "
            "100_km_or_more. For a grouped comparison with no requested order, sort by the most useful "
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
            "fixed-snapshot semantics from the generation contract.",
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
            "rows. Separate observation from cautious interpretation and state causal limitations.",
        ),
        (
            "human",
            "Question: {question}\nSQL: {sql}\nColumns: {columns}\nRows: {rows}",
        ),
    ]
)
