from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp


@dataclass
class ValidationResult:
    passed: bool
    statement_type: str
    reason: str | None = None
    failed_rule: str | None = None
    rule_action: str | None = None


def _statement_type_name(expression: exp.Expression) -> str:
    if isinstance(expression, (exp.Select, exp.Union, exp.Subquery)):
        return "SELECT"
    key = expression.key.upper()
    if key == "TRUNCATETABLE":
        return "TRUNCATE"
    if key.endswith("TABLE") and key not in ("SELECT",):
        return key.replace("TABLE", "")
    return key


def validate_sql(query: str, allowed_statement_types: list[str]) -> ValidationResult:
    allowed = {t.upper() for t in allowed_statement_types}

    try:
        statements = sqlglot.parse(query.strip())
    except Exception as exc:
        return ValidationResult(
            passed=False,
            statement_type="UNKNOWN",
            reason=f"SQL parse error: {exc}",
            failed_rule="ast_allowlist",
            rule_action="BLOCK",
        )

    if not statements:
        return ValidationResult(
            passed=False,
            statement_type="UNKNOWN",
            reason="Empty or unparseable SQL",
            failed_rule="ast_allowlist",
            rule_action="BLOCK",
        )

    if len(statements) > 1:
        types = [_statement_type_name(stmt) for stmt in statements if stmt is not None]
        return ValidationResult(
            passed=False,
            statement_type=types[0] if types else "UNKNOWN",
            reason=f"Multiple statements detected ({len(statements)}); only single statements allowed",
            failed_rule="ast_allowlist",
            rule_action="BLOCK",
        )

    statement = statements[0]
    if statement is None:
        return ValidationResult(
            passed=False,
            statement_type="UNKNOWN",
            reason="Empty or unparseable SQL",
            failed_rule="ast_allowlist",
            rule_action="BLOCK",
        )

    stmt_type = _statement_type_name(statement)

    if stmt_type not in allowed:
        return ValidationResult(
            passed=False,
            statement_type=stmt_type,
            reason=f"{stmt_type} statement not in allowlist {sorted(allowed)}",
            failed_rule="ast_allowlist",
            rule_action="BLOCK",
        )

    return ValidationResult(
        passed=True,
        statement_type=stmt_type,
        reason=None,
    )


def check_max_length(value: str, limit: int) -> ValidationResult:
    length = len(value)
    if length > limit:
        return ValidationResult(
            passed=False,
            statement_type="LENGTH",
            reason=f"Value length {length} exceeds limit {limit}",
            failed_rule="max_length",
            rule_action="BLOCK",
        )
    return ValidationResult(
        passed=True,
        statement_type="LENGTH",
        reason=None,
    )
