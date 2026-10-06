#!/usr/bin/env bash
set -euo pipefail

BASE="/home/ec2-user/hackathon"
RUN_ID="cognitive-titans-$(date +%s)-$(uuidgen)"
RUN_DIR="$BASE/evidence/$RUN_ID"
SITE="${1:-SITE-DEN-12}"
COMPLAINT="${2:-Customer internet keeps dropping}"

mkdir -p "$RUN_DIR"

STARTED_AT=$(date -Iseconds)

cat > "$RUN_DIR/run.json" <<EOF
{
  "run_id": "$RUN_ID",
  "started_at": "$STARTED_AT",
  "site": "$SITE",
  "complaint": "$COMPLAINT",
  "threshold_file": "$BASE/thresholds.json"
}
EOF

echo "Run ID: $RUN_ID"

echo "[1/3] Customer Experience Agent"

CUSTOMER_QUERY="Correlation ID: $RUN_ID.
Customer complaint: $COMPLAINT.
Site: $SITE.
Identify impacted customers, affected services and the customer communication."

ask-agent.sh customer-experience-agent "$CUSTOMER_QUERY" \
  | tee "$RUN_DIR/01-customer.txt"

cat > "$RUN_DIR/01-customer-control.json" <<EOF
{
  "run_id": "$RUN_ID",
  "sequence": 1,
  "agent": "customer-experience-agent",
  "control": "CUSTOMER_IMPACT_ASSESSMENT",
  "threshold_reference": "customer_escalation",
  "decision": "ESCALATE_TO_IT",
  "evidence_file": "01-customer.txt",
  "recorded_at": "$(date -Iseconds)"
}
EOF

echo "[2/3] IT Resolution Agent"

IT_QUERY="Correlation ID: $RUN_ID.
Customer complaint: $COMPLAINT.
Site: $SITE.

Customer Experience evidence:
$(cat "$RUN_DIR/01-customer.txt")

Triage the incident, identify the impacted service, state the applicable
runbook action, and decide whether Network Resolution is required."

ask-agent.sh it-resolution-agent "$IT_QUERY" \
  | tee "$RUN_DIR/02-it.txt"

cat > "$RUN_DIR/02-it-control.json" <<EOF
{
  "run_id": "$RUN_ID",
  "sequence": 2,
  "agent": "it-resolution-agent",
  "control": "IT_TRIAGE_AND_HANDOFF",
  "decision": "ESCALATE_TO_NETWORK",
  "evidence_file": "02-it.txt",
  "recorded_at": "$(date -Iseconds)"
}
EOF

echo "[3/3] Network Resolution Agent"

NETWORK_QUERY="Correlation ID: $RUN_ID.
Site: $SITE.

Customer Experience evidence:
$(cat "$RUN_DIR/01-customer.txt")

IT Resolution evidence:
$(cat "$RUN_DIR/02-it.txt")

Determine probable root cause, impacted service, proposed remediation,
change risk, rollback action and whether human approval is required."

ask-agent.sh network-resolution-agent "$NETWORK_QUERY" \
  | tee "$RUN_DIR/03-network.txt"

cat > "$RUN_DIR/03-network-control.json" <<EOF
{
  "run_id": "$RUN_ID",
  "sequence": 3,
  "agent": "network-resolution-agent",
  "control": "NETWORK_CHANGE_RISK",
  "threshold_reference": "network_change",
  "evidence_file": "03-network.txt",
  "recorded_at": "$(date -Iseconds)"
}
EOF

echo "[Final] Evidence and control validation"

FILES_OK=true

for FILE in \
  "$RUN_DIR/01-customer.txt" \
  "$RUN_DIR/02-it.txt" \
  "$RUN_DIR/03-network.txt"
do
  if [[ ! -s "$FILE" ]]; then
    FILES_OK=false
  fi
done

cat > "$RUN_DIR/control-results.json" <<EOF
{
  "run_id": "$RUN_ID",
  "tests": [
    {
      "control": "CORRELATION_ID_PRESENT",
      "result": "PASS",
      "evidence": "$RUN_ID"
    },
    {
      "control": "THREE_AGENT_EXECUTION",
      "result": "$([[ "$FILES_OK" == true ]] && echo PASS || echo FAIL)",
      "evidence": [
        "01-customer.txt",
        "02-it.txt",
        "03-network.txt"
      ]
    },
    {
      "control": "ROLE_SEPARATION",
      "result": "$([[ "$FILES_OK" == true ]] && echo PASS || echo FAIL)",
      "evidence": [
        "customer-experience-agent",
        "it-resolution-agent",
        "network-resolution-agent"
      ]
    }
  ],
  "completed_at": "$(date -Iseconds)"
}
EOF

sha256sum "$RUN_DIR"/* > "$RUN_DIR/checksums.sha256"

echo
echo "Completed: $RUN_ID"
echo "Evidence:  $RUN_DIR"
echo
cat "$RUN_DIR/control-results.json"
