#!/usr/bin/env bash
# Lab 5 demo: runs the four required checks and prints evidence. Usage: ./demo.sh [kube-context]
set -uo pipefail
CTX="${1:-kind-lectures}"
k() { kubectl --context "$CTX" "$@"; }
step() { printf '\n\n########## %s ##########\n' "$*"; }
cd "$(dirname "$0")/deploy"

step "0. Validation: DatabaseBackup without spec.schedule must be rejected"
k create --dry-run=server -f databasebackup-invalid.yaml 2>&1 || true

step "1. CronJob is created for the existing DatabaseBackup; changing spec.schedule updates the SAME CronJob"
k -n demo get databasebackup,cronjob
UID_BEFORE=$(k -n demo get cronjob users-db-backup -o jsonpath='{.metadata.uid}')
k -n demo patch databasebackup users-db-backup --type=merge -p '{"spec":{"schedule":"*/5 * * * *"}}'
sleep 5
k -n demo get databasebackup,cronjob
UID_AFTER=$(k -n demo get cronjob users-db-backup -o jsonpath='{.metadata.uid}')
echo "CronJob UID before=$UID_BEFORE after=$UID_AFTER (same object: $([ "$UID_BEFORE" = "$UID_AFTER" ] && echo yes || echo NO))"

step "2. Delete the managed CronJob -> the controller recreates it"
k -n demo delete cronjob users-db-backup
sleep 5
k -n demo get cronjob
k -n demo logs deploy/databasebackup-controller | tail -6

step "3a. Manual Job from the CronJob template, wait for completion, logs"
k -n demo delete job backup-manual --ignore-not-found
k -n demo create job backup-manual --from=cronjob/users-db-backup
k -n demo wait --for=condition=complete job/backup-manual --timeout=120s
k -n demo logs job/backup-manual

step "3b. Helper Pod with PostgreSQL client: list archive, restore into an empty DB, show the control record"
k -n demo delete pod pg-restore-helper --ignore-not-found >/dev/null
k -n demo apply -f - <<'EOF'
apiVersion: v1
kind: Pod
metadata:
  name: pg-restore-helper
spec:
  restartPolicy: Never
  containers:
    - name: pg
      image: postgres:16-alpine
      command: ["sleep", "600"]
      envFrom:
        - secretRef: { name: users-db-connection }
      volumeMounts:
        - { name: backups, mountPath: /backups }
  volumes:
    - name: backups
      persistentVolumeClaim: { claimName: postgres-backups }
EOF
k -n demo wait --for=condition=Ready pod/pg-restore-helper --timeout=90s
k -n demo exec pg-restore-helper -- sh -c '
  set -e
  f=$(ls -1t /backups/*.dump | head -1)
  echo "Archive: $f"; ls -lh /backups
  echo "--- pg_restore --list ---"; pg_restore --list "$f" | head -20
  echo "--- restore into empty DB users_restore ---"
  psql -d postgres -c "DROP DATABASE IF EXISTS users_restore" -c "CREATE DATABASE users_restore"
  pg_restore -d users_restore "$f"
  echo "--- control record in restored DB ---"
  psql -d users_restore -c "SELECT * FROM users"
'
k -n demo delete pod pg-restore-helper --wait=false

step "4. RBAC of the controller ServiceAccount (expected: yes, yes, no)"
SA="system:serviceaccount:demo:databasebackup-controller"
printf 'list databasebackups: '; k auth can-i list databasebackups.backup.example.com -n demo --as="$SA"
printf 'create cronjobs:      '; k auth can-i create cronjobs.batch -n demo --as="$SA"
printf 'list secrets:         '; k auth can-i list secrets -n demo --as="$SA"

step "Who creates what"
echo "DatabaseBackup (custom resource) --[our controller]--> CronJob --[kube-controller-manager: CronJob controller]--> Job --[kube-controller-manager: Job controller]--> Pod"
