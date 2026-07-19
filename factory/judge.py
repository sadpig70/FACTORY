"""Mechanical pass/fail judging of a probe result (Decision 2).

The verdict derives only from: the raw PAO ResultContract, the probe workspace
state, and the verifier-recorded publish time. No semantic OA judgment; the
``validate --record`` path is deliberately not used here.

pass_criteria vocabulary:
  result_status    -- result["status"] equals the expected terminal status.
  artifact_matches -- for each {path_basename, sha256}, some result artifact
                      OBJECT matches on basename(path) and sha256.
  artifact_absent  -- each path (relative to the probe workspace) does not exist
                      (canary check for honest-terminal / cancelled probes).
  min_elapsed_s    -- (result submitted_at - verifier publish time) >= threshold.
                      PAO results carry no started_at, so the start reference is
                      the verifier's recorded publish time (Decision 2 deviation).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .common import parse_utc


def _judge_result_status(criteria: dict[str, Any], result: dict[str, Any]) -> list[dict[str, Any]]:
    expected = criteria["result_status"]
    actual = result.get("status")
    return [
        {
            "criterion": "result_status",
            "passed": actual == expected,
            "expected": expected,
            "actual": actual,
        }
    ]


def _judge_artifact_matches(criteria: dict[str, Any], result: dict[str, Any]) -> list[dict[str, Any]]:
    # Result artifacts are the objects `complete` snapshots: {path, sha256, ...}.
    # Legacy string artifacts carry no sha256 and can never satisfy a match.
    objects = [a for a in result.get("artifacts", []) if isinstance(a, dict)]
    checks: list[dict[str, Any]] = []
    for spec in criteria["artifact_matches"]:
        want_name = spec["path_basename"]
        want_hash = spec["sha256"]
        matched = any(
            os.path.basename(str(art.get("path", ""))) == want_name and art.get("sha256") == want_hash
            for art in objects
        )
        checks.append(
            {
                "criterion": "artifact_matches",
                "passed": matched,
                "path_basename": want_name,
                "sha256": want_hash,
            }
        )
    return checks


def _judge_artifact_absent(criteria: dict[str, Any], workspace: Path) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for rel in criteria["artifact_absent"]:
        exists = (workspace / rel).exists()
        checks.append(
            {
                "criterion": "artifact_absent",
                "passed": not exists,
                "path": rel,
                "exists": exists,
            }
        )
    return checks


def _judge_min_elapsed(criteria: dict[str, Any], result: dict[str, Any], publish_time: Any) -> list[dict[str, Any]]:
    threshold = criteria["min_elapsed_s"]
    submitted_at = result.get("submitted_at")
    elapsed: float | None = None
    reason: str | None = None
    if publish_time is None:
        reason = "no_publish_time"
    elif not submitted_at:
        reason = "no_submitted_at"
    else:
        start = publish_time if hasattr(publish_time, "tzinfo") else parse_utc(str(publish_time))
        elapsed = (parse_utc(str(submitted_at)) - start).total_seconds()
    return [
        {
            "criterion": "min_elapsed_s",
            "passed": elapsed is not None and elapsed >= threshold,
            "threshold_s": threshold,
            "elapsed_s": elapsed,
            "reason": reason,
        }
    ]


SCORED_KINDS = ("result_status", "artifact_matches")


def judge_scored(scored: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Graded correctness over the IMMUTABLE result object only.

    Each weighted sub-criterion reuses a result-object sub-judge (never the live
    workspace — artifact_absent is forbidden here). score = passing-weight /
    total-weight, in [0, 1].
    """
    checks: list[dict[str, Any]] = []
    passed_weight = 0.0
    total_weight = 0.0
    for sub in scored["criteria"]:
        weight = float(sub["weight"])
        total_weight += weight
        kind = sub["kind"]
        spec = sub["spec"]
        if kind == "result_status":
            sub_checks = _judge_result_status({"result_status": spec["result_status"]}, result)
        else:  # artifact_matches (conformance restricts kinds to SCORED_KINDS)
            sub_checks = _judge_artifact_matches({"artifact_matches": [spec]}, result)
        ok = bool(sub_checks) and all(check["passed"] for check in sub_checks)
        if ok:
            passed_weight += weight
        checks.append({"kind": kind, "weight": weight, "passed": ok, "detail": sub_checks})
    score = (passed_weight / total_weight) if total_weight > 0 else None
    return {"score": score, "checks": checks}


def judge_result(
    pass_criteria: dict[str, Any],
    result: dict[str, Any],
    workspace: str | Path,
    publish_time: Any = None,
) -> dict[str, Any]:
    """Evaluate every present criterion; a probe passes only if ALL pass."""
    workspace = Path(workspace)
    checks: list[dict[str, Any]] = []
    if "result_status" in pass_criteria:
        checks += _judge_result_status(pass_criteria, result)
    if "artifact_matches" in pass_criteria:
        checks += _judge_artifact_matches(pass_criteria, result)
    if "artifact_absent" in pass_criteria:
        checks += _judge_artifact_absent(pass_criteria, workspace)
    if "min_elapsed_s" in pass_criteria:
        checks += _judge_min_elapsed(pass_criteria, result, publish_time)
    passed = bool(checks) and all(check["passed"] for check in checks)
    return {"passed": passed, "checks": checks}
