"""Replay current rules beside saved Laya predictions on one frozen diagnostic split.

Saved model predictions are not new inference or independent accuracy evidence.
"""

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from arch_review.research_fact_input import CACHE_NAMES
from arch_review.rules_v2 import evaluate_check
from arch_review.schema_v2 import CheckInput


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def score(rows):
    by_check = defaultdict(lambda: {"count": 0, "correct": 0, "false_supported": 0,
                                    "missed_contradictions": 0})
    for row in rows:
        bucket = by_check[row["check_id"]]
        bucket["count"] += 1
        bucket["correct"] += row["predicted"] == row["expected"]
        bucket["false_supported"] += row["predicted"] == "supported" and row["expected"] != "supported"
        bucket["missed_contradictions"] += (row["expected"] == "contradicted"
                                            and row["predicted"] != "contradicted")
    counts = {"count": len(rows), "correct": sum(r["predicted"] == r["expected"] for r in rows),
              "false_supported": sum(r["predicted"] == "supported" and r["expected"] != "supported"
                                     for r in rows),
              "missed_contradictions": sum(r["expected"] == "contradicted" and r["predicted"] != "contradicted"
                                            for r in rows)}
    counts["accuracy"] = counts["correct"] / counts["count"] if counts["count"] else None
    return {"overall": counts, "per_check": dict(by_check)}


def run(dataset, model_reports):
    manifest = dataset / "manifest.json"
    manifest_sha256 = hashlib.sha256(manifest.read_bytes()).hexdigest()
    exported = [json.loads(line) for line in (dataset / "experimental-development.jsonl")
                .read_text(encoding="utf-8").splitlines() if line.strip()]
    expected_ids = {row["id"] for row in exported}
    if len(expected_ids) != len(exported):
        raise ValueError("Duplicate development IDs")
    cache_fields = {external: internal for internal, external in CACHE_NAMES.items()}
    rules = []
    for row in exported:
        check_id = next(iter(row["questions"]))
        facts = json.loads(row["state"])["facts"]
        if check_id == "cache_freshness":
            facts = {cache_fields.get(key, key): value for key, value in facts.items()}
        finding = evaluate_check(CheckInput(check_id=check_id, facts=facts))
        rules.append({"id": row["id"], "check_id": check_id,
                      "expected": row["expected"][check_id], "predicted": finding.verdict.value})
    scores = {"current_rules": score(rules)}
    for name, report_path in model_reports.items():
        report = read_json(report_path)
        report_manifest = report.get("dataset_manifest_sha256")
        if report_manifest is None:
            # Trial reports inherit the frozen dataset identity from their parent run.
            run_dir = report_path.parent.parent
            plan_path = run_dir / "plan.json"
            freeze = read_json(run_dir / "input-freeze.json")
            report_manifest = read_json(plan_path)["dataset_manifest_sha256"]
            if freeze["plan"]["dataset_sha256"] != report_manifest:
                raise ValueError(f"{name} has a changed parent plan")
        if report_manifest != manifest_sha256:
            raise ValueError(f"{name} was evaluated on a different dataset manifest")
        saved = report["results"]
        if len(saved) != len(exported) or {row["id"] for row in saved} != expected_ids:
            raise ValueError(f"{name} did not cover the same development cases")
        truth = {row["id"]: (row["check_id"], row["expected"]) for row in rules}
        if any((row["check_id"], row["expected"]) != truth[row["id"]] for row in saved):
            raise ValueError(f"{name} labels do not match the exported split")
        scores[name] = {**score(saved), "saved_predictions": True,
                        "answer_order_changed_fraction": (sum(bool(row.get("changed")) for row in saved) / len(saved)),
                        "answer_order_coverage": (sum(bool(row.get("perturbation_complete")) for row in saved)
                                                  / len(saved)),
                        "publication_allowed": report.get("publication_allowed", False)}
    return {"dataset_manifest_sha256": manifest_sha256,
            "dataset_role": "ai_reviewed_synthetic_development_diagnostic",
            "independent_human_review": False, "new_model_inference": False,
            "same_case_count": len(exported), "scores": scores,
            "caution": "Template-based cases and saved development predictions cannot establish real-world accuracy."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--published", type=Path, required=True)
    parser.add_argument("--experimental", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.dataset, {"published_laya": args.published,
                                "experimental_laya": args.experimental})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
