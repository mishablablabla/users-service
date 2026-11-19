#!/usr/bin/env bash
# Lab 3: etcd quorum experiments on the kind cluster "lectures" (3 control-plane + 2 workers).
# Follows the lab text step by step; the leader / survivor nodes are detected automatically.
# Usage: ./run-lab3.sh   (cluster must exist: kind create cluster --config kind-cluster.yaml --retain)
set -uo pipefail
CTX=kind-lectures
k() { kubectl --context "$CTX" "$@"; }
step() { printf '\n\n########## %s  [%s] ##########\n' "$*" "$(date +%H:%M:%S)"; }

ETCD_NODE=lectures-control-plane
etcd() {
  local cid
  cid=$(docker exec "$ETCD_NODE" crictl ps --name etcd -q)
  if [ -z "$cid" ]; then echo "Running etcd container not found on $ETCD_NODE"; return 1; fi
  MSYS_NO_PATHCONV=1 docker exec "$ETCD_NODE" \
    crictl exec "$cid" etcdctl \
    --endpoints=https://127.0.0.1:2379 \
    --cacert=/etc/kubernetes/pki/etcd/ca.crt \
    --cert=/etc/kubernetes/pki/etcd/healthcheck-client.crt \
    --key=/etc/kubernetes/pki/etcd/healthcheck-client.key \
    --dial-timeout=3s --command-timeout=10s "$@"
}

# Prints "<leader-name> <term>" using JSON output of the (live) ETCD_NODE
leader_info() {
  # Uses the local node's view (works even while one member is paused, unlike --cluster)
  local st mem
  st=$(etcd endpoint status -w json 2>/dev/null) || return 1
  mem=$(etcd member list -w json 2>/dev/null) || mem='{"members":[]}'
  python3 -c '
import json, sys
st, mem = json.loads(sys.argv[1]), json.loads(sys.argv[2])
names = {m["ID"]: m.get("name", "?") for m in mem["members"]}
s = st[0]["Status"]
if s["leader"]:
    print(names.get(s["leader"], hex(s["leader"])), s["header"]["raft_term"])
' "$st" "$mem"
}

wait_for_leader() {  # retry while elections are in progress
  local out
  for _ in $(seq 1 12); do
    out=$(leader_info) && [ -n "$out" ] && { echo "$out"; return 0; }
    sleep 5
  done
  return 1
}

cd "$(dirname "$0")"

step "Task 1: versions and cluster"
kind version; kubectl version --client; docker info --format 'Cgroup={{.CgroupVersion}}'
k version 2>&1 | grep -i server
k get nodes -o wide
k -n kube-system get pods -o wide

step "Task 2: etcd data dir, manifest, membership, leader"
MSYS_NO_PATHCONV=1 docker exec lectures-control-plane ls -lah /var/lib/etcd/member/
MSYS_NO_PATHCONV=1 docker exec lectures-control-plane cat /etc/kubernetes/manifests/etcd.yaml
etcd member list --write-out=table
etcd endpoint status --cluster --write-out=table
etcd endpoint health --cluster
read -r LEADER TERM_BEFORE <<<"$(wait_for_leader)"
echo ">>> STATE before failure: 3 of 3, leader=$LEADER term=$TERM_BEFORE"

step "Task 3: baseline write with quorum 3/3"
k delete namespace etcd-lab --ignore-not-found   # clean re-run
k create namespace etcd-lab
k -n etcd-lab create configmap quorum-baseline --from-literal=stage=three
etcd get /registry/configmaps/etcd-lab/ --prefix --keys-only

FAILED_NODE="$LEADER"
OTHERS=$(printf '%s\n' lectures-control-plane lectures-control-plane2 lectures-control-plane3 | grep -vx "$FAILED_NODE")
SURVIVOR_NODE=$(echo "$OTHERS" | sed -n 1p)
SECOND_NODE=$(echo "$OTHERS" | sed -n 2p)
ETCD_NODE="$SURVIVOR_NODE"
echo "FAILED_NODE(leader)=$FAILED_NODE SURVIVOR_NODE=$SURVIVOR_NODE SECOND_NODE=$SECOND_NODE"

step "Task 3: pause the leader ($FAILED_NODE) -> 2 of 3 left"
docker pause "$FAILED_NODE"
sleep 10
etcd endpoint status --cluster --write-out=table || true
etcd endpoint status --write-out=table
etcd member list --write-out=table
read -r LEADER2 TERM2 <<<"$(wait_for_leader)"
echo ">>> STATE after first failure: 2 of 3, leader=$LEADER2 term=$TERM2"
for i in 1 2 3; do
  k --request-timeout=20s -n etcd-lab create configmap quorum-two --from-literal=stage=two && break
  echo "retry $i (API server behind LB may need a moment)"; sleep 8
done
k --request-timeout=20s -n etcd-lab get configmap quorum-two -o yaml

step "Task 4: pause the second node ($SECOND_NODE) -> 1 of 3, quorum lost"
docker pause "$SECOND_NODE"
date +%H:%M:%S
etcd endpoint status --write-out=table
etcd endpoint health
echo "--- kubectl create (10s timeout) ---"
START=$(date +%s)
k --request-timeout=10s -n etcd-lab create configmap quorum-lost --from-literal=stage=one
echo "(exit=$? after $(( $(date +%s) - START ))s)"
echo "--- direct etcd write / linearizable read / serializable read ---"
etcd put /lab/quorum/probe no-quorum
echo "(put exit=$?)"
etcd get /lab/quorum/probe --consistency=l
echo "(linearizable get exit=$?)"
etcd get /lab/quorum/probe --consistency=s
echo "(serializable get exit=$?)"

step "Task 5: recovery"
docker unpause "$SECOND_NODE"
sleep 10
etcd endpoint health
etcd endpoint status --cluster --write-out=table
read -r LEADER3 TERM3 <<<"$(wait_for_leader)"
echo ">>> STATE after first recovery: 2 of 3, leader=$LEADER3 term=$TERM3"
k --request-timeout=20s -n etcd-lab get configmap quorum-lost
etcd get /lab/quorum/probe
for i in 1 2 3; do
  k --request-timeout=20s -n etcd-lab create configmap quorum-restored --from-literal=stage=restored && break
  sleep 8
done
docker unpause "$FAILED_NODE"
sleep 20
etcd endpoint health --cluster
etcd endpoint status --cluster --write-out=table
read -r LEADER4 TERM4 <<<"$(wait_for_leader)"
echo ">>> STATE after full recovery: 3 of 3, leader=$LEADER4 term=$TERM4"
k -n etcd-lab get configmap
k get nodes

step "SUMMARY (fill the report table from here)"
echo "Before failure          | 3 of 3        | leader=$LEADER term=$TERM_BEFORE"
echo "After first failure     | 2 of 3        | leader=$LEADER2 term=$TERM2"
echo "After second failure    | 1 of 3        | no leader / no quorum (see Task 4 output)"
echo "After recovery          | 2 of 3 -> 3/3 | leader=$LEADER3 term=$TERM3 -> leader=$LEADER4 term=$TERM4"
