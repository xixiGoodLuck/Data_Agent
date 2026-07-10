from langchain_core.prompts import ChatPromptTemplate

REWRITE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Rewrite the latest analytics question as a self-contained request. Use recent history "
            "only to resolve references. Never add tables, filters, or facts not present in the input.",
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
            "database qualifiers, PRAGMA statements, or write operations. Use explicit joins.",
        ),
        ("human", "Question: {question}\nSchema:\n{schema_context}"),
    ]
)

SQL_REPAIR_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Repair the SQLite SELECT using only the supplied schema and sanitized error category. "
            "Return one read-only query without comments.",
        ),
        (
            "human",
            "Question: {question}\nSchema:\n{schema_context}\nSQL: {sql}\nError: {error_type}",
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
