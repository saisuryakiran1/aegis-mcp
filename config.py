from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal, Union

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

CONFIG_PATH = Path(__file__).parent / "aegis-config.yaml"

KNOWN_RULE_TYPES = {"ast_allowlist", "max_length", "threshold_check"}


class Action(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    ESCALATE_TO_HUMAN = "ESCALATE_TO_HUMAN"


class AstAllowlistRule(BaseModel):
    type: Literal["ast_allowlist"]
    allowed_statement_types: list[str]
    action: Action


class MaxLengthRule(BaseModel):
    type: Literal["max_length"]
    parameter: str
    limit: int
    action: Action


class ThresholdCheckRule(BaseModel):
    type: Literal["threshold_check"]
    parameter: str
    max_value: float
    action: Action


Rule = Annotated[
    Union[AstAllowlistRule, MaxLengthRule, ThresholdCheckRule],
    Field(discriminator="type"),
]


class Policy(BaseModel):
    name: str
    target_tool: str
    rules: list[Rule]


class Weights(BaseModel):
    w_b: float = 0.7
    w_s: float = 0.3


class HitlConfig(BaseModel):
    webhook_url: str = ""
    review_base_url: str = "http://localhost:8000"


class AegisConfig(BaseModel):
    version: str
    weights: Weights = Field(default_factory=Weights)
    semantic_judge: Literal["stub", "anthropic"] = "stub"
    upstream_url: str = ""
    hitl: HitlConfig = Field(default_factory=HitlConfig)
    policies: list[Policy]

    @field_validator("policies", mode="after")
    @classmethod
    def validate_rule_types(cls, policies: list[Policy]) -> list[Policy]:
        for policy in policies:
            for rule in policy.rules:
                rule_type = rule.type if hasattr(rule, "type") else getattr(rule, "type", None)
                if rule_type not in KNOWN_RULE_TYPES:
                    raise ValueError(
                        f"Policy '{policy.name}' references unknown rule type '{rule_type}'. "
                        f"Known types: {sorted(KNOWN_RULE_TYPES)}"
                    )
        return policies


_config: AegisConfig | None = None


def _parse_config(data: dict) -> AegisConfig:
    """Load config dict, raising clear errors for unknown rule types."""
    for policy in data.get("policies", []):
        for rule in policy.get("rules", []):
            rule_type = rule.get("type")
            if rule_type not in KNOWN_RULE_TYPES:
                raise ValueError(
                    f"Policy '{policy.get('name', '<unnamed>')}' references unknown rule type "
                    f"'{rule_type}'. Known types: {sorted(KNOWN_RULE_TYPES)}"
                )
    try:
        return AegisConfig.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"Invalid aegis-config.yaml: {exc}") from exc


def _apply_env_overrides(cfg: AegisConfig) -> AegisConfig:
    upstream = os.environ.get("UPSTREAM_MCP_URL", cfg.upstream_url or "http://localhost:9000")
    webhook = os.environ.get("HITL_WEBHOOK_URL", cfg.hitl.webhook_url)
    review_base = os.environ.get("HITL_REVIEW_BASE_URL", cfg.hitl.review_base_url)

    if cfg.semantic_judge == "anthropic" and not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY environment variable is required when semantic_judge=anthropic"
        )

    return cfg.model_copy(
        update={
            "upstream_url": upstream,
            "hitl": cfg.hitl.model_copy(
                update={"webhook_url": webhook, "review_base_url": review_base}
            ),
        }
    )


def load_config(path: Path | None = None) -> AegisConfig:
    global _config
    config_path = path or CONFIG_PATH
    with config_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    _config = _apply_env_overrides(_parse_config(data))
    return _config


def get_config() -> AegisConfig:
    if _config is None:
        return load_config()
    return _config


def get_policy(tool_name: str) -> Policy | None:
    cfg = get_config()
    for policy in cfg.policies:
        if policy.target_tool == tool_name:
            return policy
    return None
