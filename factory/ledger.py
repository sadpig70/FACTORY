"""The match ledger: ``factory.match.v1`` entries with lazy-cache invalidation.

An entry records a verified (or failed) pairing of a harness version, a model,
and a runtime version. It is keyed ``<harness>@<ver>__<model-id>.json`` under
``$FACTORY_ROOT/ledger/`` (Decision 3). Evidence is COPIED under
``ledger/evidence/<pairing>/`` because probe buses are disposable.

Lazy verification (Decision 4): a cached entry short-circuits re-measurement
only while it is ``verified``, its invalidation keys still match, and it is
within ``max_age_days``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import atomic_write_json, load_json, parse_utc, safe_token, utc_now

SCHEMA_VERSION = "factory.match.v1"
DEFAULT_MAX_AGE_DAYS = 30

RUNTIME_CONFORMANCE_VALUES = ("passed", "failed", "not_run")
PROBE_VERDICT_VALUES = ("verified", "failed", "unverified")


def pairing_key(harness_name: str, harness_version: str, model_id: str) -> str:
    return f"{safe_token(harness_name)}@{safe_token(harness_version)}__{safe_token(model_id)}"


def ledger_dir(factory_root: str | Path) -> Path:
    return Path(factory_root) / "ledger"


def entry_path(factory_root: str | Path, pairing: str) -> Path:
    return ledger_dir(factory_root) / f"{pairing}.json"


def evidence_dir(factory_root: str | Path, pairing: str) -> Path:
    return ledger_dir(factory_root) / "evidence" / pairing


def invalidation_keys(harness_version: str, model_id: str, runtime_version: str) -> dict[str, str]:
    return {
        "harness_version": harness_version,
        "model_id": model_id,
        "runtime_version": runtime_version,
    }


def make_entry(
    *,
    harness: dict[str, Any],
    model: dict[str, Any],
    runtime: dict[str, Any],
    runtime_conformance: str,
    probe_verdict: str,
    scores: dict[str, Any],
    profile: dict[str, Any],
    evidence: dict[str, Any],
    verified_at: str | None = None,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
) -> dict[str, Any]:
    """Assemble a full ``factory.match.v1`` entry (Decision 3)."""
    if runtime_conformance not in RUNTIME_CONFORMANCE_VALUES:
        raise ValueError(f"runtime_conformance must be one of {RUNTIME_CONFORMANCE_VALUES}")
    if probe_verdict not in PROBE_VERDICT_VALUES:
        raise ValueError(f"probe_verdict must be one of {PROBE_VERDICT_VALUES}")
    return {
        "schema_version": SCHEMA_VERSION,
        "harness": {
            "name": harness["name"],
            "version": harness["version"],
            "contract": harness["contract"],
        },
        "model": {"name": model.get("name"), "id": model["id"]},
        "runtime": {"name": runtime.get("name"), "version": runtime["version"]},
        "binding_mode": "hot",
        "runtime_conformance": runtime_conformance,
        "probe_verdict": probe_verdict,
        "soak_verdict": "not_started",
        "scores": {
            "per_probe": scores.get("per_probe", {}),
            "sample_size": scores.get("sample_size", 0),
        },
        "profile": {
            "median_task_time_s": profile.get("median_task_time_s"),
            "cost_class": profile.get("cost_class"),
            "bias_fingerprint": None,
            "sample_size": profile.get("sample_size", 0),
        },
        "model_attested": True,
        "evidence": {
            "copied_results": evidence.get("copied_results", []),
            "content_hashes": evidence.get("content_hashes", {}),
        },
        "invalidation_keys": invalidation_keys(
            harness["version"], model["id"], runtime["version"]
        ),
        "verified_at": verified_at or utc_now(),
        "expires_policy": {"on_key_change": True, "max_age_days": max_age_days},
        "production_stats": {"tasks": 0, "success_rate": None, "sample_size": 0},
    }


def write_entry(factory_root: str | Path, entry: dict[str, Any]) -> Path:
    keys = entry["invalidation_keys"]
    pairing = pairing_key(entry["harness"]["name"], keys["harness_version"], keys["model_id"])
    return atomic_write_json(entry_path(factory_root, pairing), entry)


def load_entry(factory_root: str | Path, pairing: str) -> dict[str, Any] | None:
    path = entry_path(factory_root, pairing)
    if not path.is_file():
        return None
    return load_json(path)


def invalidation_reason(
    entry: dict[str, Any],
    keys: dict[str, str] | None = None,
    now: Any = None,
) -> str | None:
    """Return why a cached entry is unusable, or None if it is still valid.

    ``keys`` (current harness_version/model_id/runtime_version) triggers a
    key-change check when provided; age is always checked against the entry's
    own ``expires_policy.max_age_days``.
    """
    if entry.get("probe_verdict") != "verified":
        return "not_verified"
    if keys is not None and entry.get("invalidation_keys") != keys:
        return "key_change"
    policy = entry.get("expires_policy") or {}
    max_age_days = policy.get("max_age_days", DEFAULT_MAX_AGE_DAYS)
    verified_at = entry.get("verified_at")
    if verified_at:
        reference = now if (now is not None and hasattr(now, "tzinfo")) else (
            parse_utc(str(now)) if now is not None else parse_utc(utc_now())
        )
        age_days = (reference - parse_utc(str(verified_at))).total_seconds() / 86400.0
        if age_days > max_age_days:
            return "expired"
    return None


def is_valid_cached(entry: dict[str, Any], keys: dict[str, str] | None = None, now: Any = None) -> bool:
    return invalidation_reason(entry, keys, now) is None
