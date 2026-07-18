"""Load and validate a ``factory.conformance.v1`` manifest.

A conformance manifest names a harness and a list of probes. Each probe binds
a PAO TaskContract template to a ``pass_criteria`` block (the mechanical
judging vocabulary of Decision 2) and to deterministic ``verifier_actions``
(Decision 6): ``drop_file`` / ``cancel`` behaviours the verifier performs but
never judges.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import load_json

SCHEMA_VERSION = "factory.conformance.v1"

PASS_CRITERIA_KINDS = ("result_status", "artifact_matches", "artifact_absent", "min_elapsed_s")
ACTION_TYPES = ("drop_file", "cancel")


class ConformanceError(ValueError):
    """Raised when a conformance manifest is structurally invalid."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ConformanceError(message)


def _validate_pass_criteria(probe_id: str, criteria: Any) -> None:
    _require(isinstance(criteria, dict), f"{probe_id}: pass_criteria must be an object")
    _require(bool(criteria), f"{probe_id}: pass_criteria must not be empty")
    unknown = set(criteria) - set(PASS_CRITERIA_KINDS)
    _require(not unknown, f"{probe_id}: unknown pass_criteria: {sorted(unknown)}")

    if "result_status" in criteria:
        _require(
            isinstance(criteria["result_status"], str) and criteria["result_status"],
            f"{probe_id}: result_status must be a non-empty string",
        )
    if "artifact_matches" in criteria:
        matches = criteria["artifact_matches"]
        _require(isinstance(matches, list) and matches, f"{probe_id}: artifact_matches must be a non-empty array")
        for spec in matches:
            _require(isinstance(spec, dict), f"{probe_id}: artifact_matches entries must be objects")
            _require(
                isinstance(spec.get("path_basename"), str) and spec["path_basename"],
                f"{probe_id}: artifact_matches entry needs a path_basename",
            )
            _require(
                isinstance(spec.get("sha256"), str) and len(spec["sha256"]) == 64,
                f"{probe_id}: artifact_matches entry needs a 64-char sha256",
            )
    if "artifact_absent" in criteria:
        absent = criteria["artifact_absent"]
        _require(isinstance(absent, list) and absent, f"{probe_id}: artifact_absent must be a non-empty array")
        for rel in absent:
            _require(isinstance(rel, str) and rel, f"{probe_id}: artifact_absent entries must be paths")
    if "min_elapsed_s" in criteria:
        value = criteria["min_elapsed_s"]
        _require(
            isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0,
            f"{probe_id}: min_elapsed_s must be a positive number",
        )


def _validate_actions(probe_id: str, actions: Any) -> None:
    _require(isinstance(actions, list), f"{probe_id}: verifier_actions must be an array")
    for action in actions:
        _require(isinstance(action, dict), f"{probe_id}: verifier_actions entries must be objects")
        kind = action.get("type")
        _require(kind in ACTION_TYPES, f"{probe_id}: unknown verifier action type: {kind!r}")
        if kind == "drop_file":
            _require(
                isinstance(action.get("path"), str) and action["path"],
                f"{probe_id}: drop_file action needs a path",
            )
            after = action.get("after_s")
            _require(
                isinstance(after, (int, float)) and not isinstance(after, bool) and after >= 0,
                f"{probe_id}: drop_file action needs a non-negative after_s",
            )
        elif kind == "cancel":
            after = action.get("after_claim_s")
            _require(
                isinstance(after, (int, float)) and not isinstance(after, bool) and after >= 0,
                f"{probe_id}: cancel action needs a non-negative after_claim_s",
            )


def validate(manifest: Any) -> dict[str, Any]:
    """Validate a parsed manifest dict; return it unchanged. Raises on error."""
    _require(isinstance(manifest, dict), "conformance manifest must be a JSON object")
    _require(
        manifest.get("schema_version") == SCHEMA_VERSION,
        f"schema_version must be {SCHEMA_VERSION!r}",
    )
    harness = manifest.get("harness")
    _require(isinstance(harness, dict), "harness must be an object")
    for key in ("name", "version", "contract"):
        _require(
            isinstance(harness.get(key), str) and harness[key],
            f"harness.{key} must be a non-empty string",
        )
    probes = manifest.get("probes")
    _require(isinstance(probes, list) and probes, "probes must be a non-empty array")
    seen: set[str] = set()
    for probe in probes:
        _require(isinstance(probe, dict), "each probe must be an object")
        probe_id = probe.get("probe_id")
        _require(isinstance(probe_id, str) and probe_id, "probe needs a probe_id")
        _require(probe_id not in seen, f"duplicate probe_id: {probe_id}")
        seen.add(probe_id)
        _require(
            isinstance(probe.get("task_template"), str) and probe["task_template"],
            f"{probe_id}: task_template must be a path string",
        )
        _validate_pass_criteria(probe_id, probe.get("pass_criteria"))
        _validate_actions(probe_id, probe.get("verifier_actions", []))
    return manifest


def load(path: str | Path) -> dict[str, Any]:
    """Load and validate a conformance manifest from disk."""
    manifest = load_json(path)
    validate(manifest)
    return manifest


def template_path(manifest_path: str | Path, probe: dict[str, Any]) -> Path:
    """Resolve a probe's task_template relative to the manifest's directory."""
    return (Path(manifest_path).resolve().parent / probe["task_template"]).resolve()
