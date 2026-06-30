import pytest

from config import load_config
from guardrails.allowlist_engine import ValidationResult
from guardrails.risk_scorer import score_call


@pytest.fixture(autouse=True)
def _load_config():
    load_config()


def _ok() -> ValidationResult:
    return ValidationResult(passed=True, statement_type="SELECT", reason=None)


def _drop() -> ValidationResult:
    return ValidationResult(
        passed=False,
        statement_type="DROP",
        reason="DROP statement not in allowlist ['SELECT']",
        failed_rule="ast_allowlist",
        rule_action="BLOCK",
    )


def _oversized() -> ValidationResult:
    return ValidationResult(
        passed=False,
        statement_type="LENGTH",
        reason="Value length 501 exceeds limit 500",
        failed_rule="max_length",
        rule_action="BLOCK",
    )


def _stacked() -> ValidationResult:
    return ValidationResult(
        passed=False,
        statement_type="SELECT",
        reason="Multiple statements detected (2); only single statements allowed",
        failed_rule="ast_allowlist",
        rule_action="BLOCK",
    )


def _threshold_payment() -> ValidationResult:
    return ValidationResult(
        passed=False,
        statement_type="THRESHOLD",
        reason="amount 150.0 exceeds max 100.0",
        failed_rule="threshold_check",
        rule_action="ESCALATE_TO_HUMAN",
    )


class TestRiskScorerWorkedExamples:
    def test_1_clean_select_semantic_safe(self):
        decision = score_call("execute_sql_query", _ok(), 0.0)
        assert decision.action == "ALLOW"

    def test_2_clean_select_semantic_medium(self):
        decision = score_call("execute_sql_query", _ok(), 0.66)
        assert decision.action == "ALLOW"

    def test_3_drop_table_semantic_safe(self):
        decision = score_call("execute_sql_query", _drop(), 0.0)
        assert decision.action == "BLOCK"

    def test_4_oversized_query_semantic_low(self):
        decision = score_call("execute_sql_query", _oversized(), 0.33)
        assert decision.action == "BLOCK"

    def test_5_payment_50_semantic_safe(self):
        decision = score_call("send_payment", _ok(), 0.0)
        assert decision.action == "ALLOW"

    def test_6_payment_150_threshold_semantic_safe(self):
        decision = score_call("send_payment", _threshold_payment(), 0.0)
        assert decision.action == "ESCALATE_TO_HUMAN"

    def test_7_payment_150_semantic_high(self):
        decision = score_call("send_payment", _threshold_payment(), 1.0)
        assert decision.action == "BLOCK"

    def test_8_unknown_tool_default_deny(self):
        decision = score_call("unknown_tool", _ok(), 0.0)
        assert decision.action == "BLOCK"

    def test_9_stacked_query_semantic_high(self):
        decision = score_call("execute_sql_query", _stacked(), 1.0)
        assert decision.action == "BLOCK"

    def test_10_clean_select_semantic_high(self):
        decision = score_call("execute_sql_query", _ok(), 1.0)
        assert decision.action == "ESCALATE_TO_HUMAN"
