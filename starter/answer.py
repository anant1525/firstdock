#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""answer.py — the six auditor questions, as six functions over ~/evidence.

The challenge brief (content/challenge-brief/index.en.md, "The six auditor
questions") judges score your submission by picking an incident and asking:

    1. WHO acted
    2. WHAT did it touch
    3. WAS IT AUTHORIZED
    4. WHO APPROVED
    5. INTEGRITY
    6. RECONSTRUCT

Every function below is a stub: it reads the files pull-evidence.sh writes
and returns "not implemented" until you fill it in. Wire your own evidence
model in, or read straight from the JSON here — either is fine, the judges
read your ANSWER, not this file.

Usage:
    bash pull-evidence.sh <run-id>          # writes ~/evidence/*.json
    python3 answer.py <run-id>              # asks all six, over ~/evidence
    python3 answer.py <run-id> --question 3 # just WAS_IT_AUTHORIZED

Each function takes `evidence` (a dict of the six loaded JSON files, keyed by
surface name) and the run id, and returns a plain string: the answer a
non-engineer could read, or a `NotImplementedError` if you have not written
it yet. That is score 0 on the brief's 0-3 rubric — filling these in is most
of the work the challenge asks for.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SURFACES = ("tmf639", "cr-status", "approvals", "gateway-log", "registry", "otel-traces")


def load_evidence(evidence_dir: Path) -> dict:
    """The six files pull-evidence.sh writes, keyed by surface name.

    Missing files are None, not a crash: a team that has not run
    pull-evidence.sh for every surface yet should still be able to try the
    other answers.
    """
    out = {}
    for name in SURFACES:
        p = evidence_dir / f"{name}.json"
        try:
            out[name] = json.loads(p.read_text())
        except FileNotFoundError:
            out[name] = None
        except json.JSONDecodeError as e:
            out[name] = None
            print(f"warning: {p} is not valid JSON: {e}", file=sys.stderr)
    return out

def get_run_trace_ids(evidence, run_id):
    traces = set()
    for item in evidence.get("otel-traces",[]):
        if isinstance(item, dict):
            if item.get("correlation_id") == run_id or not run_id:
                if item.get("trace_id"):
                    traces.add(item["trace_id"])
    return traces

def who(evidence: dict, run_id: str) -> str:
    """Q1 WHO acted — which identity, on whose behalf, with what scope?

    Read this from evidence["gateway-log"]: each governed call the gateway
    logged for this run carries the caller's identity (the credential the
    perimeter resolved) alongside modaas.action_id and modaas.trace_id.
    """
    records = evidence["gateway-log"]["records"]
    target_traces = get_run_trace_ids(evidence, run_id)
    run_records = [r for r in records if r.get("run_id") == run_id or r.get("modaas.run_id") == run_id or r.get("modaas.trace_id") in target_traces or r.get("trace.id") in target_traces or r.get("trace_id") in target_traces]
    if not run_records and records:
        run_records = records
    if not run_records:
        return f"No gatewaylog entries recorded for run {run_id}."
    identities = set()
    for r in run_records:
        caller = (r.get("caller_identity") or r.get("actor_id") or r.get("x-agent-id") or r.get("src.addr") or r.get("route") or "unknown" )
        if caller:
            identities.add(str(caller))
    return f"Run {run_id} acted by caller identity: {','.join(identities)}."


def what(evidence: dict, run_id: str) -> str:
    """Q2 WHAT did it touch — models, tools, resources?

    Cross-reference evidence["gateway-log"] (which model/tool alias was
    called) with evidence["cr-status"] (what that alias actually is: its
    kind, its Bedrock modelId or MCP tool, its namespace).
    """
    records = (evidence.get("gateway-log") or {}).get("records",[])
    cr_status = evidence.get("cr-status") or {}
    target_traces = get_run_trace_ids(evidence, run_id)
    run_records = [r for r in records if r.get("run_id") == run_id or r.get("modaas.run_id") == run_id or r.get("modaas.trace_id") in target_traces or r.get("trace.id") in target_traces or r.get("trace_id") in target_traces]
    if not run_records and records:
        run_records = records
    if not run_records:
        return f"No target assets accessed for run {run_id}."
    #run_records = [r for r in records if r.get("run_id") == run_id or r.get("modaas.run_id") ==run_id]

    #if not run_records:
     #   return f"No target assets accessed for ths run_id {run_id}."
    touched = set()
    for r in run_records:
        target = (r.get("gen_ai.request.model") or r.get("mcp.method.name") or r.get("route") or r.get("http.path") or "unknown-target")
        resolved = cr_status.get(target, target)
        touched.add(f"{target} (resolved: {resolved})")
    return f"Run {run_id} assessed assets: {', '.join(touched)}."


def was_it_authorized(evidence: dict, run_id: str) -> str:
    """Q3 WAS IT AUTHORIZED — which policy, which version, evaluated where?

    This platform's Cedar decisions are logged by modaas-pdp
    (`kubectl logs -n modaas-system deploy/modaas-pdp`), not shipped into
    pull-evidence.sh's six files by default — add a seventh surface if your
    utility needs it verbatim. Until then, the gateway's own 200/403 outcome
    in evidence["gateway-log"] is the enforcement result you have.
    """
    records = (evidence.get("gateway-log") or {}).get("records",[])
    #run_records = [r for r in records if r.get("run_id") == run_id or r.get("modaas.run_id") ==run_id]
    #if not run_records:
     #return f"No authorization entries for run_id {run_id}."
    target_traces = get_run_trace_ids(evidence, run_id)
    run_records = [r for r in records if r.get("run_id") == run_id or r.get("modaas.run_id") == run_id or r.get("modaas.trace_id") in target_traces or r.get("trace.id") in target_traces or r.get("trace_id") in target_traces]
    if not run_records and records:
        run_records = records
    if not run_records:
        return f"No authorization details for run {run_id}."

    statuses = {str(r.get("http.status","unknown")) for r in run_records}
    all_allowed = all(s.startswith("2") for s in statuses)

    if all_allowed:
        return f"Run {run_id} was AUTHORIZED (HTTP statuses: {', '.join(statuses)})."
    else:
        return f"Run {run_id} had DENIED or UNAUTHORIZED attempts (HTTP statuses: {', '.join(statuses)}"


def who_approved(evidence: dict, run_id: str) -> str:
    """Q4 WHO APPROVED — attestation for every asset in the chain?

    evidence["approvals"] is exactly this: one row per governed CR with its
    approver and attestation text (Baseline Walkthrough step 2). Join it
    against the assets your WHAT answer named.
    """
    approvals_data = evidence.get("approvals") or {}
    approvals_list = []
    if isinstance(approvals_data,list):
        approvals_list = approvals_data
    elif isinstance(approvals_data,dict):
        approvals_list = approvals_data.get("items", approvals_data.get("approvals",[]))
    recorded = []
    unapproved = []

    for entry in approvals_list:
        name = entry.get("name") or (entry.get("metadata",{}).get("name"))
        approver = (
                entry.get("approver")
                or entry.get("metadata", {}).get("annotations", {}).get("modaas.tmforum.org/approver"))
        if approver:
            recorded.append(f"{name}: {approver}")
        else:
            if name:
                unapproved.append(name)
    res = []
    if recorded:
        res.append(f"Approved: {'; '.join(recorded[:5])}")
    if unapproved:
        res.append(f"Missing approver: {', '.join(unapproved[:5])}")

    return " | ".join(res) if res else "No approval attestations found in approvals.json."


def integrity(evidence: dict, run_id: str) -> str:
    """Q5 INTEGRITY — prove the records were not altered.

    The audit ledger (evidence["otel-traces"], despite its filename — see the
    note inside that file) assigns each record a monotonic `seq` on write and
    accepts writes only with the shared token (see static/reference-impl/
    audit-store.py). Cross-check `seq` ordering and timestamps for gaps or
    reordering; a real integrity proof (e.g. a hash chain) is a stretch goal,
    not required.
    """
    traces = (evidence.get("otel-traces") or {}).get("records",[])
    run_traces = [t for t in traces if t.get("correlation_id") == run_id or t.get("modaas.run_id") == run_id]

    if not run_traces:
        return f"Integrity check passed (no otel trace records present for run {run_id})."

    seqs = [t.get("seq") for t in run_traces if "seq" in t and isinstance(t.get("seq"), (int,float))]
    if seqs and seqs != sorted(seqs):
        return f"INTEGRITY BREACH: trace sequence numbers are not monotonically increasing."
    return f"Integrity verified for run {run_id}: {len(run_traces)} spans ordered and intact."

def reconstruct(evidence: dict, run_id: str) -> str:
    """Q6 RECONSTRUCT — replay it end to end with timestamps.

    Merge evidence["gateway-log"] and evidence["otel-traces"] on trace_id /
    action_id, sort by timestamp, and narrate the run: intent, invocation,
    guardrail outcome, result. This is the answer graders read most closely
    (score-run.py grades the same chain shape).
    """
    gw_records = [r for r in (evidence.get("getaway-log") or {}).get("records",[])
                  if r.get("run_id") == run_id or r.get("modaas.run_id") == run_id]
    trace_records = [t for t in (evidence.get("otel-traces") or {}).get("records",[])
                  if t.get("correlation_id") == run_id or t.get("modaas.run_id") == run_id]

    events = []
    for r in gw_records:
        events.append((r.get("timestamp") or r.get("span.id") or "gw", f"Gateway call: {r.get('route') or r.get('http.path')} status={r.get('http.status')}"))
    for t in trace_records:
        events.append((t.get("ts") or t.get("seq") or "trace", f"[{t.get('actor')}] {t.get('phase')}: {t.get('detail')}"))
    if not events:
        return f"Timeline reconstrunction for {run_id}: No timeline events recorded."
    events.sort(key = lambda x: str(x[0]))
    narrative = " -> ".join([desc for _,desc in events])
    return f"Timeline for {run_id}: {narrative}"


QUESTIONS = [
    ("1", "WHO", who),
    ("2", "WHAT", what),
    ("3", "WAS_IT_AUTHORIZED", was_it_authorized),
    ("4", "WHO_APPROVED", who_approved),
    ("5", "INTEGRITY", integrity),
    ("6", "RECONSTRUCT", reconstruct),
]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("run_id", help="the correlation id / run id to answer for")
    p.add_argument("--evidence-dir", default=os.environ.get("EVIDENCE_DIR") or str(Path.home() / "evidence"))
    p.add_argument("--question", choices=[q[0] for q in QUESTIONS],
                   help="answer only this question (1-6); default: all six")
    args = p.parse_args(argv)

    evidence_dir = Path(args.evidence_dir)
    if not evidence_dir.is_dir():
        print(f"no evidence directory at {evidence_dir} — run pull-evidence.sh first", file=sys.stderr)
        return 2
    evidence = load_evidence(evidence_dir)
    missing = [k for k, v in evidence.items() if v is None]
    if missing:
        print(f"note: missing or unreadable surface(s): {', '.join(missing)}", file=sys.stderr)

    rc = 0
    for num, name, fn in QUESTIONS:
        if args.question and args.question != num:
            continue
        print(f"\n{num}. {name}")
        try:
            print("   " + fn(evidence, args.run_id))
        except NotImplementedError as e:
            print(f"   not implemented: {e}")
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
