from app.agent.prompts import REWRITE_PROMPT, SQL_GENERATION_PROMPT, SQL_REPAIR_PROMPT


def _system_text(prompt) -> str:
    return str(prompt.messages[0].prompt.template)


def test_rewrite_contract_prevents_filter_leakage() -> None:
    text = _system_text(REWRITE_PROMPT)

    assert "preserve it verbatim" in text
    assert "never copy prior filters" in text


def test_sql_contract_covers_snapshot_and_output_shape() -> None:
    text = _system_text(SQL_GENERATION_PROMPT)

    assert "fixed snapshot" in text
    assert "never reinterpret it with SQLite now/current-date functions" in text
    assert "do not add a time predicate" in text
    assert "Never use date('now')" in text
    assert "Project only the dimensions and measures requested" in text
    assert "ASCII lowercase English snake_case" in text
    assert "sort by the most useful aggregate descending" in text
    assert "MUST use conditional aggregation" in text
    assert "Do not self-join" in text
    assert "dataset_id" in SQL_GENERATION_PROMPT.input_variables


def test_repair_contract_receives_dataset_identifier() -> None:
    assert "dataset_id" in SQL_REPAIR_PROMPT.input_variables
