"""Small, explicit order-processing cases from the Claude connector walkthrough.

These are developer-authored regressions, not independently reviewed accuracy data.
"""

import pytest

from arch_review.rules_v2 import evaluate_check
from arch_review.schema_v2 import CheckInput

RETRY_REQUIREMENT = {"prevent_duplicate_effects": True}
RETRY_DESIGN = {
    "redelivery_possible": True,
    "all_effects_intrinsically_idempotent": False,
    "stable_message_id": True,
    "dedup_enforced": True,
    "dedup_atomic_with_effect": True,
    "dedup_retention_seconds": 30 * 24 * 3600,
    "max_redelivery_age_seconds": 24 * 3600,
    "external_effects": True,
}
ACK_REQUIREMENT = {"acknowledged_operation": "order durably stored", "survive_failures": ["host_loss"]}
QUEUE_REQUIREMENT = {"preserve_accepted_messages": True, "bounded_queue_required": True}


CASES = [
    ("payment-retry-without-provider-protection", "retry_safety",
     {"requirements": RETRY_REQUIREMENT,
      "design": {"retry": {**RETRY_DESIGN, "external_effects_idempotent": False}}}, "contradicted"),
    ("payment-retry-with-provider-protection-declared", "retry_safety",
     {"requirements": RETRY_REQUIREMENT,
      "design": {"retry": {**RETRY_DESIGN, "external_effects_idempotent": True}}}, "supported"),
    ("payment-retry-provider-protection-unknown", "retry_safety",
     {"requirements": RETRY_REQUIREMENT, "design": {"retry": RETRY_DESIGN}}, "insufficient_information"),
    ("api-ack-after-memory-enqueue", "ack_durability",
     {"requirements": ACK_REQUIREMENT,
      "design": {"acknowledgement": {"acknowledged_operation": "enqueued in memory",
                                      "after_durable_commit": False, "survives_failures": []}}}, "contradicted"),
    ("api-ack-after-replicated-commit-declared", "ack_durability",
     {"requirements": ACK_REQUIREMENT,
      "design": {"acknowledgement": {"acknowledged_operation": "order durably stored",
                                      "after_durable_commit": True, "survives_failures": ["host_loss"]}}}, "supported"),
    ("api-ack-failure-coverage-unknown", "ack_durability",
     {"requirements": ACK_REQUIREMENT,
      "design": {"acknowledgement": {"acknowledged_operation": "order durably stored",
                                      "after_durable_commit": True}}}, "insufficient_information"),
    ("unbounded-order-queue", "queue_overload",
     {"requirements": QUEUE_REQUIREMENT,
      "design": {"queue": {"policy": "unbounded", "preserves_accepted_messages": True}}}, "contradicted"),
    ("bounded-order-queue-policy-declared", "queue_overload",
     {"requirements": QUEUE_REQUIREMENT,
      "design": {"queue": {"policy": "reject_before_accept", "max_messages": 60000,
                           "admission_before_accept": True, "preserves_accepted_messages": True,
                           "retry_backoff": True}}}, "supported"),
    ("bounded-order-queue-admission-unknown", "queue_overload",
     {"requirements": QUEUE_REQUIREMENT,
      "design": {"queue": {"policy": "reject_before_accept", "max_messages": 60000,
                           "preserves_accepted_messages": True, "retry_backoff": True}}},
     "insufficient_information"),
]


@pytest.mark.parametrize("name, check_id, facts, expected", CASES, ids=[row[0] for row in CASES])
def test_order_processing_diagnostic(name, check_id, facts, expected):
    finding = evaluate_check(CheckInput(check_id=check_id, scope_id=name, facts=facts))
    assert finding.verdict == expected
    assert bool(finding.missing_information) == (expected == "insufficient_information")
