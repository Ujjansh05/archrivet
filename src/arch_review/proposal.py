"""Conditional rule checks for an assistant's proposed architecture.

Every supplied design fact is treated as an assumption. This deliberately does
not upgrade assistant-authored text into a user declaration or a deployed fact.
"""

from pydantic import Field, model_validator

from .documents import flatten
from .rules_v2 import evaluate_check
from .schema import Deployment, ReviewRequest, StrictModel, Workload
from .schema_v2 import CheckInput
from .workload import calculate


class ProposalCheck(StrictModel):
    check_id: str
    scope_id: str = Field(default="design", min_length=1, max_length=128)
    applicable: bool | None = True
    facts: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_facts(self):
        checked = CheckInput(check_id=self.check_id, scope_id=self.scope_id,
                             applicable=self.applicable, facts=self.facts)
        self.facts = checked.facts
        return self


class ProposalPreviewRequest(StrictModel):
    checks: list[ProposalCheck] = Field(min_length=1, max_length=32)
    workload: Workload = Field(default_factory=Workload)
    deployment: Deployment = Field(default_factory=Deployment)

    @model_validator(mode="after")
    def unique_scopes(self):
        keys = [(check.scope_id, check.check_id) for check in self.checks]
        if len(keys) != len(set(keys)):
            raise ValueError("Proposal scope/check pairs must be unique")
        return self


def preview_proposal(request: ProposalPreviewRequest) -> dict:
    """Evaluate proposed facts conditionally with deterministic rules only."""
    findings = []
    for check in request.checks:
        item = CheckInput(check_id=check.check_id, scope_id=check.scope_id,
                          applicable=check.applicable, facts=check.facts)
        finding = evaluate_check(item)
        findings.append({
            "check_id": check.check_id,
            "scope_id": check.scope_id,
            "evaluation_status": finding.evaluation_status,
            "conditional_verdict": finding.verdict.value if finding.verdict is not None else None,
            "reason": finding.reason,
            "missing_information": finding.missing_information,
            "assumed_facts": flatten(check.facts),
            "verification_steps": finding.verification_steps,
        })
    estimates, capacity = calculate(ReviewRequest(requirements={}, design={},
        workload=request.workload, deployment=request.deployment))
    return {
        "status": "hypothetical_preview",
        "model_used": False,
        "deployment_verified": False,
        "facts_verified": False,
        "check_count": len(findings),
        "checks": findings,
        "workload_estimates": estimates,
        "capacity": capacity,
        "interpretation": (
            "Each conditional verdict holds only if every assumed fact for that check is true. "
            "A supported preview is not evidence that the design was implemented or tested."
        ),
    }
