"""verify-pairing: drive the PAO OA CLI over a disposable probe bus.

The verifier publishes each probe as an ordinary PAO TaskContract with
``--lwar-id`` (Decision 1), performs the deterministic ``verifier_actions``
(drop a release file, cancel mid-run), polls ``collect`` for the result,
judges it mechanically, copies the evidence out of the disposable bus, and
writes the ledger entry — ``probe_verdict=verified`` only when EVERY probe
passes. A quarantined result is an automatic probe FAIL.

The OA CLI is reached through an injectable ``runner`` callable
(``argv -> emitted-JSON-event``) so tests stub the whole bus. Time is reached
through injectable ``monotonic``/``sleep`` so tests never wait on the clock.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

from . import conformance as conformance_module
from . import ledger as ledger_module
from .common import atomic_write_json, copy_into, load_json, utc_now

Runner = Callable[[list[str]], dict[str, Any]]


def make_subprocess_runner(pao_cli: str | Path, python: str | None = None) -> Runner:
    """Production runner: ``python <pao_cli> *argv`` -> parsed last JSON line.

    The OA CLI emits one JSON object per line; the terminal event is the last
    non-empty line. Errors (non-zero exit) surface as RuntimeError so the
    verifier fails closed rather than mis-judging a silent bus fault.
    """
    interpreter = python or sys.executable
    cli = str(Path(pao_cli))

    def run(argv: list[str]) -> dict[str, Any]:
        completed = subprocess.run(
            [interpreter, cli, *argv],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"pao cli failed ({completed.returncode}): {argv}\n{completed.stderr.strip()}"
            )
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        if not lines:
            raise RuntimeError(f"pao cli produced no output: {argv}")
        return json.loads(lines[-1])

    return run


def _publish_task(
    *,
    manifest_path: str | Path,
    probe: dict[str, Any],
    workspace: Path,
    runner: Runner,
    lwar_id: str,
    bus_root: str,
) -> tuple[str, str]:
    """Write the probe TaskContract with cwd bound to its workspace; publish it."""
    workspace.mkdir(parents=True, exist_ok=True)
    template = load_json(conformance_module.template_path(manifest_path, probe))
    template["cwd"] = str(workspace)
    template.setdefault(
        "permissions", {"read": [str(workspace)], "write": [str(workspace)], "network": False}
    )
    task_file = workspace / "_factory_task.json"
    atomic_write_json(task_file, template)
    publish_time = utc_now()
    event = runner(["send", "--lwar-id", lwar_id, "--task-file", str(task_file), "--root", bus_root])
    task_id = event.get("task_id")
    if not task_id:
        raise RuntimeError(f"send did not return a task_id for probe {probe['probe_id']}: {event}")
    return task_id, publish_time


def _apply_action(
    action: dict[str, Any],
    workspace: Path,
    runner: Runner,
    lwar_id: str,
    task_id: str,
    bus_root: str,
) -> None:
    if action["type"] == "drop_file":
        target = workspace / action["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("released-by-verifier\n", encoding="utf-8")
    elif action["type"] == "cancel":
        runner(
            [
                "control",
                "--lwar-id",
                lwar_id,
                "--command",
                "cancel",
                "--task-id",
                task_id,
                "--root",
                bus_root,
            ]
        )


def _find(entries: list[dict[str, Any]], task_id: str) -> dict[str, Any] | None:
    for entry in entries:
        if entry.get("task_id") == task_id:
            return entry
    return None


def _find_result(results: list[dict[str, Any]], task_id: str) -> dict[str, Any] | None:
    for entry in results:
        if (entry.get("result") or {}).get("task_id") == task_id:
            return entry
    return None


def _collect_until_result(
    *,
    probe: dict[str, Any],
    task_id: str,
    workspace: Path,
    runner: Runner,
    lwar_id: str,
    bus_root: str,
    poll_timeout_s: float,
    poll_interval_s: float,
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
) -> dict[str, Any]:
    """Poll collect, firing verifier_actions on schedule. Returns an outcome dict.

    outcome: {"kind": "result", "result": {...}, "result_file": str}
           | {"kind": "quarantined", "reason": str, "file": str}
           | {"kind": "timeout"}
    """
    actions = probe.get("verifier_actions", [])
    fired = [False] * len(actions)
    start = monotonic()
    while True:
        elapsed = monotonic() - start
        for index, action in enumerate(actions):
            if fired[index]:
                continue
            # after_s is relative to publish; after_claim_s is measured from the
            # same reference in the MVP (file-bus claim latency ~= poll interval).
            trigger = action.get("after_s", action.get("after_claim_s", 0))
            if elapsed >= trigger:
                _apply_action(action, workspace, runner, lwar_id, task_id, bus_root)
                fired[index] = True
        collected = runner(["collect", "--lwar-id", lwar_id, "--root", bus_root])
        quarantined = _find(collected.get("quarantined", []), task_id)
        if quarantined is not None:
            return {"kind": "quarantined", "reason": quarantined.get("reason"), "file": quarantined.get("file")}
        result_entry = _find_result(collected.get("results", []), task_id)
        if result_entry is not None:
            return {
                "kind": "result",
                "result": result_entry["result"],
                "result_file": result_entry.get("result_file"),
            }
        if monotonic() - start >= poll_timeout_s:
            return {"kind": "timeout"}
        sleep(poll_interval_s)


def _copy_evidence(
    factory_root: str | Path,
    pairing: str,
    probe_id: str,
    result_file: str | None,
) -> tuple[list[str], dict[str, str]]:
    if not result_file or not Path(result_file).is_file():
        return [], {}
    destination_dir = ledger_module.evidence_dir(factory_root, pairing) / probe_id
    copied, digest = copy_into(result_file, destination_dir)
    relative = f"{probe_id}/{copied.name}"
    return [relative], {relative: digest}


def verify_pairing(
    *,
    manifest: dict[str, Any],
    manifest_path: str | Path,
    model: dict[str, Any],
    runtime: dict[str, Any],
    lwar_id: str,
    bus_root: str,
    workspace_root: str | Path,
    factory_root: str | Path,
    runner: Runner,
    runtime_conformance: str = "not_run",
    poll_timeout_s: float = 200.0,
    poll_interval_s: float = 5.0,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Run every probe, judge mechanically, copy evidence, write the ledger entry."""
    from . import judge as judge_module

    harness = manifest["harness"]
    workspace_root = Path(workspace_root)
    pairing = ledger_module.pairing_key(harness["name"], harness["version"], model["id"])

    probes_report: dict[str, Any] = {}
    copied_results: list[str] = []
    content_hashes: dict[str, str] = {}
    all_passed = True

    for probe in manifest["probes"]:
        probe_id = probe["probe_id"]
        workspace = workspace_root / probe_id
        task_id, publish_time = _publish_task(
            manifest_path=manifest_path,
            probe=probe,
            workspace=workspace,
            runner=runner,
            lwar_id=lwar_id,
            bus_root=bus_root,
        )
        outcome = _collect_until_result(
            probe=probe,
            task_id=task_id,
            workspace=workspace,
            runner=runner,
            lwar_id=lwar_id,
            bus_root=bus_root,
            poll_timeout_s=poll_timeout_s,
            poll_interval_s=poll_interval_s,
            monotonic=monotonic,
            sleep=sleep,
        )

        if outcome["kind"] == "result":
            verdict = judge_module.judge_result(
                probe["pass_criteria"], outcome["result"], workspace, publish_time
            )
            passed = verdict["passed"]
            probe_copied, probe_hashes = _copy_evidence(
                factory_root, pairing, probe_id, outcome.get("result_file")
            )
            copied_results += probe_copied
            content_hashes.update(probe_hashes)
            probes_report[probe_id] = {
                "passed": passed,
                "outcome": "result",
                "task_id": task_id,
                "checks": verdict["checks"],
            }
        elif outcome["kind"] == "quarantined":
            passed = False
            probe_copied, probe_hashes = _copy_evidence(
                factory_root, pairing, probe_id, outcome.get("file")
            )
            copied_results += probe_copied
            content_hashes.update(probe_hashes)
            probes_report[probe_id] = {
                "passed": False,
                "outcome": "quarantined",
                "task_id": task_id,
                "reason": outcome.get("reason"),
            }
        else:  # timeout
            passed = False
            probes_report[probe_id] = {
                "passed": False,
                "outcome": "timeout",
                "task_id": task_id,
            }
        all_passed = all_passed and passed

    probe_verdict = "verified" if (all_passed and manifest["probes"]) else "failed"
    per_probe_scores = {pid: report["passed"] for pid, report in probes_report.items()}
    entry = ledger_module.make_entry(
        harness=harness,
        model=model,
        runtime=runtime,
        runtime_conformance=runtime_conformance,
        probe_verdict=probe_verdict,
        scores={"per_probe": per_probe_scores, "sample_size": len(probes_report)},
        profile={"median_task_time_s": None, "cost_class": None, "sample_size": 0},
        evidence={"copied_results": copied_results, "content_hashes": content_hashes},
    )
    entry_path = ledger_module.write_entry(factory_root, entry)

    return {
        "event": "verify_pairing_complete",
        "pairing": pairing,
        "probe_verdict": probe_verdict,
        "probes": probes_report,
        "entry_path": str(entry_path),
    }
