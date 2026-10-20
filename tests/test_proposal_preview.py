"""A proposal can be checked conditionally without becoming a deployed fact."""

from arch_review.proposal import ProposalPreviewRequest, preview_proposal


def test_ack_proposal_flips_conditionally_and_never_verifies_deployment():
    def check(after_commit):
        return {"check_id": "ack_durability", "scope_id": "orders", "facts": {
            "requirements": {"acknowledged_operation": "order durably stored",
                             "survive_failures": ["host_loss"]},
            "design": {"acknowledgement": {"acknowledged_operation": "order durably stored",
                                            "after_durable_commit": after_commit,
                                            "survives_failures": ["host_loss"]}},
        }}

    failed = preview_proposal(ProposalPreviewRequest(checks=[check(False)]))
    passed = preview_proposal(ProposalPreviewRequest(checks=[check(True)]))
    assert failed["checks"][0]["conditional_verdict"] == "contradicted"
    assert passed["checks"][0]["conditional_verdict"] == "supported"
    for result in (failed, passed):
        assert result["status"] == "hypothetical_preview"
        assert result["model_used"] is False
        assert result["deployment_verified"] is False
        assert result["facts_verified"] is False
        assert result["checks"][0]["assumed_facts"]["design.acknowledgement.after_durable_commit"] is not None


def test_missing_proposal_fact_remains_missing():
    proposal = ProposalPreviewRequest(checks=[{"check_id": "queue_overload", "facts": {
        "requirements": {"bounded_queue_required": True, "preserve_accepted_messages": True},
        "design": {"queue": {"policy": "reject_before_accept"}},
    }}])
    result = preview_proposal(proposal)["checks"][0]
    assert result["conditional_verdict"] == "insufficient_information"
    assert result["missing_information"]


def test_duplicate_proposal_scope_is_rejected():
    item = {"check_id": "cache_freshness", "scope_id": "prices", "facts": {"max_staleness_ms": 5000}}
    try:
        ProposalPreviewRequest(checks=[item, item])
    except ValueError as exc:
        assert "unique" in str(exc)
    else:
        raise AssertionError("Duplicate proposals must be rejected")
