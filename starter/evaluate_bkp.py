#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""evaluate.py — the control test tool the challenge brief asks you to bring.

    python3 evaluate.py <control-id> <run-id> [--evidence-dir DIR] [--register FILE]

Stateless: given a control id (matching an entry in register.yaml) and a run
id, it pulls the evidence pull-evidence.sh already wrote to ~/evidence/*.json,
compares the measured value against the register's threshold for that
control, and returns PASS or BREACH with the record ids behind the number.

This is deliberately the fourth part the brief requires ("a control test
that returns a verdict"), not a dashboard: it prints one verdict line and
exits 0 (PASS), 1 (BREACH) or 2 (NO EVIDENCE for that run), so it composes into a script or a CI step.

Only control "16" (per-run token spend cap) is implemented here, because it
is the one metric fully computable from the evidence pull-evidence.sh ships
today (the gateway's own token/cost fields). Controls 7 and 9 are stubs:
extend `_METRICS` with your own function once your evidence model covers
them — the register entry and the CLI plumbing are already there.

Usage:
    bash pull-evidence.sh fault-1758900000
    python3 evaluate.py 16 fault-1758900000
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None


def _load_register(path: Path) -> dict:
    text = path.read_text()
    if yaml is not None:
        doc = yaml.safe_load(text)
        controls = {str(c["control_id"]): c for c in doc.get("controls", [])}
        return controls
    # No PyYAML on this box: register.yaml's shape is simple enough (one
    # list of flat mappings) to parse the fields evaluate.py needs without
    # a real YAML parser, so the tool still runs on a bare Python install.
    controls, cur = {}, None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line.lstrip().startswith("- control_id:"):
            if cur:
                controls[str(cur["control_id"])] = cur
            cur = {"control_id": line.split(":", 1)[1].strip().strip('"\'')}
        elif cur is not None and ":" in line:
            k, v = line.strip().split(":", 1)
            v = v.strip().strip('"\'')
            cur[k] = v
    if cur:
        controls[str(cur["control_id"])] = cur
    return controls


def _load_evidence(evidence_dir: Path) -> dict:
    out = {}
    for name in ("tmf639", "cr-status", "approvals", "gateway-log", "registry", "otel-traces"):
        p = evidence_dir / f"{name}.json"
        try:
            out[name] = json.loads(p.read_text())
        except FileNotFoundError:
            out[name] = None
    return out


def _control_16_token_spend(evidence: dict, run_id: str, threshold: dict) -> tuple[str, str]:
    """Sum input+output tokens across every gateway-log record for this run.

    Returns (verdict, detail). detail names the call/action ids the verdict
    rests on, per the brief's "a control test ... that answers ... with the
    call ids behind the number".
    """
    gw = evidence.get("gateway-log") or {"records": []}
    records = [r for r in gw.get("records", []) if r.get("modaas.run_id") == run_id]
    total = 0
    call_ids = []
    for r in records:
        try:
            total += int(r.get("gen_ai.usage.input_tokens", 0))
            total += int(r.get("gen_ai.usage.output_tokens", 0))
        except (TypeError, ValueError):
            pass
        aid = r.get("modaas.action_id")
        if aid:
            call_ids.append(aid)
    if not records:
        return "NO EVIDENCE", (f"no gateway-log record for run {run_id} in the evidence "
                               f"directory; run pull-evidence.sh {run_id} first (a run "
                               f"with no records is not a pass)")
    limit = threshold.get("observation_limit")
    try:
        limit = float(limit)
    except (TypeError, ValueError):
        return "BREACH", (f"register.yaml has no numeric observation_limit for control 16 "
                          f"(got {limit!r}) — fill it in before scoring")
    verdict = "PASS" if total <= limit else "BREACH"
    detail = (f"{total} tokens across {len(records)} call(s) (limit {limit:g}); "
             f"call ids: {', '.join(call_ids) if call_ids else 'none recorded'}")
    return verdict, detail

def _control_7_coverage(evidence: dict, run_id:str,threshold: dict) -> tuple[str, str]:
    traces = (evidence.get("otel-traces") or {}).get("records",[])
    records = [
            t for t in traces
            if t.get("correlation_id") == run_id or t.get("modaas.run_id") == run_id
            ]
    if not records:
        return "NO EVIDENCE", f"no otel-trace records for run {run_id}"
    expected_phases = {"intent","invocation","result-inspection"}
    expected_agents = {"customer-experience-agent","it-resolution-agent","network-resolution-agent","fault-orchestrator-agent"}

    observed ={}
    for r in records:
        actor = r.get("actor")
        phase = str(r.get("phase","")).lower()
        if actor:
            observed.setdefault(actor,set()).add(phase)
    total_slots = len(expected_agents) * len(expected_phases)
    covered_slots = 0
    missing = []

    for agent in expected_agents:
        agent_phases = observed.get(agent, set())
        for p in expected_phases:
            if p in agent_phases:
                covered_slots += 1
            else:
                missing.append(f"{agent}:{p}")
    coverage = covered_slots/total_slots if total_slots else 0.0

    try:
        limit = float(threshold.get("observation_limit", 1.0))
    except (TypeError,ValueError):
        return "BREACH","register.yaml has not no numeric observation_limit for control 7"

    verdict = "PASS" if coverage >=limit else "BREACH"
    detail = (
            f"event coverage {coverage:.2f} ({covered_slots}/{total_slots} required phases recorded, limit {limit:g});"
            f"missing: {', '.join(missing) if missing else 'none'}"
        )
    return verdict,detail

# Extend this table as you implement controls 7 and 9. Each function takes
# (evidence, run_id, threshold_entry) and returns (verdict, detail) exactly
# like _control_16_token_spend.
_METRICS = {
    "16": _control_16_token_spend,
    "7": _control_7_coverage
}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("control_id")
    p.add_argument("run_id")
    p.add_argument("--evidence-dir", default=str(Path.home() / "evidence"))
    p.add_argument("--register", default=str(Path(__file__).with_name("register.yaml")))
    args = p.parse_args(argv)

    register_path = Path(args.register)
    if not register_path.is_file():
        print(f"no register at {register_path} — copy register.yaml and fill in your thresholds", file=sys.stderr)
        return 2
    controls = _load_register(register_path)
    entry = controls.get(str(args.control_id))
    if entry is None:
        print(f"control {args.control_id!r} is not in {register_path} "
              f"(have: {', '.join(sorted(controls)) or 'none'})", file=sys.stderr)
        return 2
    fn = _METRICS.get(str(args.control_id))
    if fn is None:
        print(f"control {args.control_id!r} has a register entry but no metric function in "
              f"evaluate.py's _METRICS — add one (see _control_16_token_spend for the shape)",
              file=sys.stderr)
        return 2

    evidence_dir = Path(args.evidence_dir)
    if not evidence_dir.is_dir():
        print(f"no evidence directory at {evidence_dir} — run pull-evidence.sh first", file=sys.stderr)
        return 2
    evidence = _load_evidence(evidence_dir)

    verdict, detail = fn(evidence, args.run_id, entry)
    owner = entry.get("owner", "?")
    version_date = entry.get("version_date", "?")
    print(f"control {args.control_id} ({entry.get('name', '?')})  run {args.run_id}")
    print(f"threshold owner={owner} version_date={version_date}")
    print(f"{verdict}: {detail}")
    return {"PASS": 0, "NO EVIDENCE": 2}.get(verdict, 1)


if __name__ == "__main__":
    sys.exit(main())
