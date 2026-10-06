#!/bin/bash

CID=$1

echo "===== TRACEABILITY REPORT ====="

kubectl get --raw \
"/api/v1/namespaces/components/services/audit-store:8080/proxy/timeline?cid=$CID"
