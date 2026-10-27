"""Validate and summarize an external blind benchmark result.

Raw Qloo-backed outputs stay outside git. BENCHMARK.md freezes the protocol and
neutral rubric. Set QLOO_BENCHMARK_RESULT to the external JSON result path.
"""
from __future__ import annotations

import json
import os
import pathlib

CRITERIA = ("relevance", "specificity", "feasibility", "decision_usefulness")
RUBRIC = {
    "relevance": "Directly answers the question and stays internally coherent.",
    "specificity": "Gives concrete choices that a team could execute.",
    "feasibility": "Respects real product constraints and avoids unsupported predictions.",
    "decision_usefulness": "Gives a practical comparison, test, metric, or stopping rule.",
}
ARMS = ("model_only", "qloo_plus_model")


def validate(payload):
    if payload.get("answer_calls", 0) < 1:
        raise ValueError("The model-only arm did not make a real model call.")
    if payload.get("grader_model_family") == payload.get("answer_model"):
        raise ValueError("The blind grader must use a different model family.")
    rows = payload.get("rows") or []
    if len(rows) != 5:
        raise ValueError("Expected five frozen questions.")
    seen = set()
    calculated = {arm: {criterion: 0 for criterion in CRITERIA} | {"total": 0} for arm in ARMS}
    for row in rows:
        answers = row.get("answers") or []
        if {answer.get("arm") for answer in answers} != set(ARMS):
            raise ValueError("Each question needs both arms.")
        for answer in answers:
            blind_id = answer.get("blind_id")
            if not blind_id or blind_id in seen:
                raise ValueError("Blind IDs must be present and unique.")
            seen.add(blind_id)
            scores = answer.get("scores") or {}
            if set(scores) != set(CRITERIA) or any(not 1 <= scores[key] <= 5 for key in CRITERIA):
                raise ValueError("Every neutral criterion must score from 1 to 5.")
            arm = answer["arm"]
            for criterion in CRITERIA:
                calculated[arm][criterion] += scores[criterion]
            calculated[arm]["total"] += sum(scores[criterion] for criterion in CRITERIA)
    if payload.get("totals") != calculated:
        raise ValueError("Reported totals do not match answer scores.")
    return calculated


def run(path=None):
    value = path or os.environ.get("QLOO_BENCHMARK_RESULT")
    if not value:
        raise SystemExit("Set QLOO_BENCHMARK_RESULT to the external result JSON.")
    source = pathlib.Path(value)
    payload = json.loads(source.read_text())
    validate(payload)
    return payload


if __name__ == "__main__":
    result = run()
    print(json.dumps({"totals": result["totals"], "verdict": result["verdict"]}, indent=2))
