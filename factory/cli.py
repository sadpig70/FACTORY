"""factory CLI: verify-pairing | bind | ledger-show.

verify-pairing drives the probe pipeline (with a lazy-cache short-circuit).
bind is the verified-only gate (Decision 5) that emits a BindingInstruction.
ledger-show inspects stored match entries.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from . import conformance as conformance_module
from . import ledger as ledger_module
from . import verifier as verifier_module
from .common import resolve_root

BINDING_SCHEMA = "factory.binding-instruction.v1"


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), flush=True)


def command_verify_pairing(args: argparse.Namespace) -> int:
    factory_root = resolve_root(args.root)
    manifest_path = Path(args.conformance).resolve()
    manifest = conformance_module.load(manifest_path)
    harness = manifest["harness"]
    model = {"name": args.model_name, "id": args.model_id}
    runtime = {"name": args.runtime_name, "version": args.runtime_version}

    pairing = ledger_module.pairing_key(harness["name"], harness["version"], model["id"])
    keys = ledger_module.invalidation_keys(harness["version"], model["id"], runtime["version"])
    if not args.force:
        cached = ledger_module.load_entry(factory_root, pairing)
        if cached is not None and ledger_module.is_valid_cached(cached, keys):
            _emit(
                {
                    "event": "verify_pairing_cached",
                    "pairing": pairing,
                    "probe_verdict": cached["probe_verdict"],
                    "verified_at": cached["verified_at"],
                    "entry_path": str(ledger_module.entry_path(factory_root, pairing)),
                }
            )
            return 0

    runner = verifier_module.make_subprocess_runner(args.pao_cli)
    result = verifier_module.verify_pairing(
        manifest=manifest,
        manifest_path=manifest_path,
        model=model,
        runtime=runtime,
        lwar_id=args.lwar_id,
        bus_root=str(Path(args.bus_root).resolve()),
        workspace_root=Path(args.workspace).resolve(),
        factory_root=factory_root,
        runner=runner,
        runtime_conformance=args.runtime_conformance,
        poll_timeout_s=args.poll_timeout,
        poll_interval_s=args.poll_interval,
    )
    _emit(result)
    return 0 if result["probe_verdict"] == "verified" else 2


def command_bind(args: argparse.Namespace) -> int:
    factory_root = resolve_root(args.root)
    if args.pairing:
        pairing = args.pairing
    else:
        pairing = ledger_module.pairing_key(args.harness, args.harness_version, args.model_id)
    entry = ledger_module.load_entry(factory_root, pairing)
    if entry is None:
        _emit({"event": "bind_refused", "pairing": pairing, "reason": "no_ledger_entry"})
        return 3

    keys = None
    if args.runtime_version is not None:
        # Bind against a specific runtime version: a mismatch invalidates the
        # cached pairing (key change) and the gate must refuse.
        keys = dict(entry.get("invalidation_keys", {}))
        keys["runtime_version"] = args.runtime_version
    reason = ledger_module.invalidation_reason(entry, keys)
    if reason is not None:
        _emit({"event": "bind_refused", "pairing": pairing, "reason": reason})
        return 2

    harness = entry["harness"]
    instruction = {
        "schema_version": BINDING_SCHEMA,
        "event": "binding_instruction",
        "pairing": pairing,
        "binding_mode": entry["binding_mode"],
        "harness": harness,
        "model": entry["model"],
        "runtime": entry["runtime"],
        "bus_root": str(Path(args.bus_root).resolve()) if args.bus_root else None,
        "contract": harness["contract"],
        "register_args": [
            "register",
            "--runtime-name",
            entry["runtime"].get("name") or "",
            "--model",
            entry["model"].get("name") or "",
        ],
        "verified_at": entry["verified_at"],
        "expires_policy": entry["expires_policy"],
    }
    _emit(instruction)
    return 0


def command_ledger_show(args: argparse.Namespace) -> int:
    factory_root = resolve_root(args.root)
    if args.pairing:
        entry = ledger_module.load_entry(factory_root, args.pairing)
        if entry is None:
            _emit({"event": "ledger_entry_missing", "pairing": args.pairing})
            return 3
        _emit({"event": "ledger_entry", "pairing": args.pairing, "entry": entry})
        return 0

    directory = ledger_module.ledger_dir(factory_root)
    entries = []
    if directory.is_dir():
        for path in sorted(directory.glob("*.json")):
            entry = ledger_module.load_entry(factory_root, path.stem)
            if entry is None:
                continue
            entries.append(
                {
                    "pairing": path.stem,
                    "probe_verdict": entry.get("probe_verdict"),
                    "runtime_conformance": entry.get("runtime_conformance"),
                    "verified_at": entry.get("verified_at"),
                }
            )
    _emit({"event": "ledger_list", "count": len(entries), "entries": entries})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="factory", description="Agent Factory MVP CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    verify = subparsers.add_parser("verify-pairing")
    verify.add_argument("--conformance", required=True)
    verify.add_argument("--model-id", required=True)
    verify.add_argument("--model-name", default=None)
    verify.add_argument("--runtime-name", default=None)
    verify.add_argument("--runtime-version", required=True)
    verify.add_argument("--lwar-id", required=True)
    verify.add_argument("--bus-root", required=True)
    verify.add_argument("--workspace", required=True)
    verify.add_argument("--pao-cli", required=True)
    verify.add_argument("--root", default=None)
    verify.add_argument(
        "--runtime-conformance",
        default="not_run",
        choices=ledger_module.RUNTIME_CONFORMANCE_VALUES,
    )
    verify.add_argument("--poll-timeout", type=float, default=200.0)
    verify.add_argument("--poll-interval", type=float, default=5.0)
    verify.add_argument("--force", action="store_true", help="ignore any valid cached entry")
    verify.set_defaults(handler=command_verify_pairing)

    bind = subparsers.add_parser("bind")
    bind.add_argument("--pairing", default=None)
    bind.add_argument("--harness", default=None)
    bind.add_argument("--harness-version", default=None)
    bind.add_argument("--model-id", default=None)
    bind.add_argument("--runtime-version", default=None)
    bind.add_argument("--bus-root", default=None)
    bind.add_argument("--root", default=None)
    bind.set_defaults(handler=command_bind)

    show = subparsers.add_parser("ledger-show")
    show.add_argument("--pairing", default=None)
    show.add_argument("--root", default=None)
    show.set_defaults(handler=command_ledger_show)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "bind" and not args.pairing:
        if not (args.harness and args.harness_version and args.model_id):
            build_parser().error("bind requires --pairing or all of --harness/--harness-version/--model-id")
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
