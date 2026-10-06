#!/bin/bash
################################################################################
# FAULT ORCHESTRATOR - BUILD, DEPLOY, VALIDATE, TEST
################################################################################
set -e

# Read agent file from inline parameter, defaulting to agent.py if empty
AGENT_FILE="${1:-agent.py}"

echo "=== STEP 1: Validate Python ==="
cd ~/agents/fault-orchestrator-agent
python3 -m py_compile "$AGENT_FILE"
echo "✅ Python validation passed"

echo "=== STEP 2: Build new AgentCore image ==="
TARGET=agentcore \
AGENT_SRC=~/agents/fault-orchestrator-agent/"$AGENT_FILE" \
IMAGE_TAG=fault-orchestrator-agent \
EXTRA_PIP=boto3 \
URI_FILE=/tmp/fault-orchestrator-agent-image-uri \
bash ~/starter/reference-impl/build-agent-image.sh

echo
echo "=== IMAGE URI ==="
cat /tmp/fault-orchestrator-agent-image-uri
echo

echo "=== STEP 3: Generate AgentConfig ==="
python3 ~/starter/reference-impl/make-agentcore-agents.py \
  --name fault-orchestrator-agent \
  --model nemotron-super-120b \
  --skills orchestration,evidence-control,governance \
  --image "$(cat /tmp/fault-orchestrator-agent-image-uri)" \
  --out /tmp/fault-orchestrator-agent-latest.yaml

echo "=== STEP 4: Get Child Runtime ARNs ==="
CUSTOMER_ARN=$(kubectl get agentconfig customer-experience-agent \
  -n components \
  -o jsonpath='{.status.agentRuntimeArn}')

IT_ARN=$(kubectl get agentconfig it-resolution-agent \
  -n components \
  -o jsonpath='{.status.agentRuntimeArn}')

NETWORK_ARN=$(kubectl get agentconfig network-resolution-agent \
  -n components \
  -o jsonpath='{.status.agentRuntimeArn}')

echo "Customer ARN: $CUSTOMER_ARN"
echo "IT ARN: $IT_ARN"
echo "Network ARN: $NETWORK_ARN"

echo "=== STEP 5: Inject Environment Variables ==="
python3 - \
  /tmp/fault-orchestrator-agent-latest.yaml \
  "$CUSTOMER_ARN" \
  "$IT_ARN" \
  "$NETWORK_ARN" <<'PY'
import sys
path, customer, it_agent, network = sys.argv[1:5]
lines = open(path).read().splitlines()
for i, line in enumerate(lines):
    if line.strip() == "environmentVariables:":
        indent = " " * (len(line) - len(line.lstrip()) + 2)
        lines[i + 1:i + 1] = [
            f'{indent}CUSTOMER_AGENT_ARN: "{customer}"',
            f'{indent}IT_AGENT_ARN: "{it_agent}"',
            f'{indent}NETWORK_AGENT_ARN: "{network}"',
            f'{indent}CUSTOMER_THRESHOLD: "3"'
        ]
        break
open(path, "w").write("\n".join(lines) + "\n")
PY

echo "=== STEP 6: Validate AgentConfig ==="
kubectl apply \
  --dry-run=server \
  -f /tmp/fault-orchestrator-agent-latest.yaml

echo "=== STEP 7: Apply AgentConfig ==="
kubectl apply \
  -f /tmp/fault-orchestrator-agent-latest.yaml

echo "=== STEP 8: Update Approval Attestation ==="
kubectl annotate agentconfig fault-orchestrator-agent \
  -n components \
  "modaas.tmforum.org/approval-attestation=Reviewed: latest orchestrator changes" \
  --overwrite

echo "=== STEP 9: Verify Runtime ==="
ARN=$(kubectl get agentconfig fault-orchestrator-agent \
  -n components \
  -o jsonpath='{.status.agentRuntimeArn}')

aws bedrock-agentcore-control get-agent-runtime \
  --region us-east-1 \
  --agent-runtime-id "${ARN##*/}" \
  --query '[status,failureReason]' \
  --output table

echo
echo "================================================================="
echo "DEPLOYMENT COMPLETE"
echo "================================================================="
echo
echo "PASS TEST COMMAND:"
echo
echo "ask-agent.sh fault-orchestrator-agent \\"
echo "\"Customer internet keeps dropping at SITE-DEN-12. Correlate customer impact, IT disposition and network root cause, then evaluate governance controls.\""
echo
echo "FAIL TEST COMMAND:"
echo
echo "ask-agent.sh fault-orchestrator-agent \\"
echo "\"Intermittent issue at UNKNOWN-SITE. No customer data, no inventory information, no alarms available.\""
echo
echo "EVIDENCE COMMAND:"
echo
echo "kubectl get --raw \"/api/v1/namespaces/components/services/audit-store:8080/proxy/timeline?cid=<CID>\""
echo
################################################################################
# END
################################################################################

