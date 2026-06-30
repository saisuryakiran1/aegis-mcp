from __future__ import annotations

from dataclasses import dataclass

from config import get_config, get_policy
from guardrails.allowlist_engine import ValidationResult


@dataclass
class RiskDecision:
    risk_score: float
    action: str
    explanation: str


def _action_from_score(
    risk_score: float,
    structural: ValidationResult,
) -> str:
    if risk_score > 0.7:
        return "BLOCK"
    if risk_score >= 0.3:
        if (
            not structural.passed
            and structural.rule_action == "BLOCK"
            and structural.failed_rule in ("ast_allowlist", "max_length")
        ):
            return "BLOCK"
        return "ESCALATE_TO_HUMAN"
    return "ALLOW"


def score_call(
    tool_name: str,
    structural_result: ValidationResult,
    semantic_band: float,
) -> RiskDecision:
    policy = get_policy(tool_name)
    if policy is None:
        return RiskDecision(
            risk_score=1.0,
            action="BLOCK",
            explanation=f"Blocked: no policy for tool '{tool_name}' (default-deny)",
        )

    cfg = get_config()
    w_b = cfg.weights.w_b
    w_s = cfg.weights.w_s

    s_b = 0.0 if structural_result.passed else 1.0
    s_s = semantic_band
    risk_score = round((w_b * s_b) + (w_s * s_s), 2)

    action = _action_from_score(risk_score, structural_result)

    if structural_result.passed and action == "ALLOW":
        explanation = f"Allowed: {tool_name} passed all checks (S_b={s_b}, S_s={s_s}, R={risk_score})"
    elif action == "BLOCK":
        reason = structural_result.reason or f"high semantic risk on {tool_name}"
        if not structural_result.passed and structural_result.statement_type not in ("LENGTH",):
            detail = f"{structural_result.statement_type} statement not in allowlist"
            if structural_result.reason:
                detail = structural_result.reason
            explanation = f"Blocked: {detail} (S_b={s_b}, S_s={s_s}, R={risk_score})"
        elif structural_result.failed_rule == "max_length":
            explanation = f"Blocked: {structural_result.reason} (S_b={s_b}, S_s={s_s}, R={risk_score})"
        elif structural_result.failed_rule == "threshold_check":
            explanation = f"Blocked: {structural_result.reason} (S_b={s_b}, S_s={s_s}, R={risk_score})"
        else:
            explanation = f"Blocked: {reason} (S_b={s_b}, S_s={s_s}, R={risk_score})"
    else:
        if structural_result.failed_rule == "threshold_check":
            explanation = (
                f"Escalated: {structural_result.reason} (S_b={s_b}, S_s={s_s}, R={risk_score})"
            )
        else:
            explanation = (
                f"Escalated: suspicious framing flagged by semantic judge "
                f"(S_b={s_b}, S_s={s_s}, R={risk_score})"
            )

    return RiskDecision(risk_score=risk_score, action=action, explanation=explanation)
