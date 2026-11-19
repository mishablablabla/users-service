"""DatabaseBackup controller (lab 5).

Watches DatabaseBackup custom resources (and the CronJobs it owns) in one namespace and
reconciles the desired state: one CronJob per DatabaseBackup, running pg_dump on a schedule.

Design:
  * level-triggered reconcile(key) - idempotent, safe to run any number of times;
  * a de-duplicating work queue, so repeated events for the same object produce one reconcile;
  * LIST + WATCH from the list's resourceVersion; the watch is re-established when it ends
    and a fresh LIST is done on 410 Gone;
  * a periodic full resync as a safety net.
"""
import hashlib
import json
import logging
import os
import queue
import threading
import time

from kubernetes import client, config, watch
from kubernetes.client.rest import ApiException

GROUP, VERSION, PLURAL, KIND = "backup.example.com", "v1alpha1", "databasebackups", "DatabaseBackup"
NAMESPACE = os.getenv("WATCH_NAMESPACE", "demo")
PG_IMAGE = os.getenv("PG_IMAGE", "postgres:16-alpine")
RESYNC_SECONDS = int(os.getenv("RESYNC_SECONDS", "60"))
HASH_ANNOTATION = "backup.example.com/spec-hash"

log = logging.getLogger("databasebackup-controller")


class WorkQueue:
    """FIFO queue that ignores a key that is already waiting (de-duplication)."""

    def __init__(self):
        self._q: "queue.Queue[str]" = queue.Queue()
        self._pending: set[str] = set()
        self._lock = threading.Lock()

    def add(self, key: str) -> None:
        with self._lock:
            if key in self._pending:
                return
            self._pending.add(key)
        self._q.put(key)

    def get(self) -> str:
        key = self._q.get()
        with self._lock:
            self._pending.discard(key)
        return key


# ---------- desired state ----------

BACKUP_SCRIPT = r"""
set -eu
ts=$(date -u +%Y%m%dT%H%M%SZ)
tmp="/backups/.${PGDATABASE}-${ts}.tmp"
out="/backups/${PGDATABASE}-${ts}.dump"
trap 'rm -f "$tmp"' EXIT
pg_dump -Fc -f "$tmp"
mv "$tmp" "$out"
echo "Backup archive written: $out"
"""


def desired_cronjob(backup: dict) -> dict:
    meta, spec = backup["metadata"], backup["spec"]
    name = meta["name"]
    body = {
        "apiVersion": "batch/v1",
        "kind": "CronJob",
        "metadata": {
            "name": name,
            "namespace": meta["namespace"],
            "labels": {"app.kubernetes.io/managed-by": "databasebackup-controller"},
            "ownerReferences": [
                {
                    "apiVersion": f"{GROUP}/{VERSION}",
                    "kind": KIND,
                    "name": name,
                    "uid": meta["uid"],
                    "controller": True,
                    "blockOwnerDeletion": True,
                }
            ],
        },
        "spec": {
            "schedule": spec["schedule"],
            "timeZone": spec.get("timeZone", "Etc/UTC"),
            "concurrencyPolicy": "Forbid",
            "successfulJobsHistoryLimit": 3,
            "failedJobsHistoryLimit": 3,
            "jobTemplate": {
                "spec": {
                    "backoffLimit": 2,
                    "template": {
                        "spec": {
                            "restartPolicy": "OnFailure",
                            "containers": [
                                {
                                    "name": "pg-dump",
                                    "image": PG_IMAGE,
                                    "command": ["sh", "-c", BACKUP_SCRIPT],
                                    "envFrom": [{"secretRef": {"name": spec["connectionSecretName"]}}],
                                    "volumeMounts": [{"name": "backups", "mountPath": "/backups"}],
                                }
                            ],
                            "volumes": [
                                {
                                    "name": "backups",
                                    "persistentVolumeClaim": {"claimName": spec["backupPVCName"]},
                                }
                            ],
                        }
                    },
                }
            },
        },
    }
    digest = hashlib.sha256(json.dumps(body["spec"], sort_keys=True).encode()).hexdigest()[:16]
    body["metadata"]["annotations"] = {HASH_ANNOTATION: digest}
    return body


# ---------- reconcile ----------


class Controller:
    def __init__(self):
        self.custom = client.CustomObjectsApi()
        self.batch = client.BatchV1Api()
        self.queue = WorkQueue()

    def reconcile(self, key: str) -> None:
        ns, name = key.split("/", 1)
        try:
            backup = self.custom.get_namespaced_custom_object(GROUP, VERSION, ns, PLURAL, name)
        except ApiException as e:
            if e.status == 404:
                log.info("%s: DatabaseBackup is gone, owned CronJob is garbage-collected", key)
                return
            raise

        desired = desired_cronjob(backup)
        try:
            current = self.batch.read_namespaced_cron_job(name, ns)
        except ApiException as e:
            if e.status != 404:
                raise
            self.batch.create_namespaced_cron_job(ns, desired)
            log.info("%s: created CronJob (schedule=%s)", key, desired["spec"]["schedule"])
            return

        owners = current.metadata.owner_references or []
        if not any(o.uid == backup["metadata"]["uid"] for o in owners):
            log.error("%s: CronJob with this name exists but is not owned by this DatabaseBackup - conflict", key)
            return

        current_hash = (current.metadata.annotations or {}).get(HASH_ANNOTATION)
        if current_hash == desired["metadata"]["annotations"][HASH_ANNOTATION]:
            log.debug("%s: CronJob up to date", key)
            return
        self.batch.patch_namespaced_cron_job(
            name,
            ns,
            {"metadata": {"annotations": desired["metadata"]["annotations"]}, "spec": desired["spec"]},
        )
        log.info("%s: updated CronJob (schedule=%s)", key, desired["spec"]["schedule"])

    # ---------- event sources ----------

    def worker(self) -> None:
        while True:
            key = self.queue.get()
            try:
                self.reconcile(key)
            except Exception:  # keep the loop alive, retry on next event/resync
                log.exception("%s: reconcile failed, will retry", key)
                time.sleep(2)
                self.queue.add(key)

    def watch_backups(self) -> None:
        while True:
            try:
                snapshot = self.custom.list_namespaced_custom_object(GROUP, VERSION, NAMESPACE, PLURAL)
                for item in snapshot["items"]:
                    self.queue.add(f"{NAMESPACE}/{item['metadata']['name']}")
                rv = snapshot["metadata"]["resourceVersion"]
                w = watch.Watch()
                try:
                    for event in w.stream(
                        self.custom.list_namespaced_custom_object,
                        GROUP, VERSION, NAMESPACE, PLURAL,
                        resource_version=rv, timeout_seconds=30,
                    ):
                        if event["type"] in {"ADDED", "MODIFIED", "DELETED"}:
                            self.queue.add(f"{NAMESPACE}/{event['object']['metadata']['name']}")
                finally:
                    w.stop()
            except ApiException as e:
                if e.status == 410:
                    log.info("DatabaseBackup watch expired (410 Gone), re-listing")
                else:
                    log.exception("DatabaseBackup watch failed")
                    time.sleep(3)
            except Exception:
                log.exception("DatabaseBackup watch failed")
                time.sleep(3)

    def watch_cronjobs(self) -> None:
        """Re-queue the owner when a managed CronJob changes or is deleted (self-healing)."""
        selector = "app.kubernetes.io/managed-by=databasebackup-controller"
        while True:
            try:
                snapshot = self.batch.list_namespaced_cron_job(NAMESPACE, label_selector=selector)
                rv = snapshot.metadata.resource_version
                w = watch.Watch()
                try:
                    for event in w.stream(
                        self.batch.list_namespaced_cron_job,
                        NAMESPACE, label_selector=selector,
                        resource_version=rv, timeout_seconds=30,
                    ):
                        self.queue.add(f"{NAMESPACE}/{event['object'].metadata.name}")
                finally:
                    w.stop()
            except ApiException as e:
                if e.status != 410:
                    log.exception("CronJob watch failed")
                    time.sleep(3)
            except Exception:
                log.exception("CronJob watch failed")
                time.sleep(3)

    def resync(self) -> None:
        while True:
            time.sleep(RESYNC_SECONDS)
            try:
                for item in self.custom.list_namespaced_custom_object(GROUP, VERSION, NAMESPACE, PLURAL)["items"]:
                    self.queue.add(f"{NAMESPACE}/{item['metadata']['name']}")
            except Exception:
                log.exception("periodic resync failed")

    def run(self) -> None:
        log.info("starting controller, namespace=%s", NAMESPACE)
        for target in (self.worker, self.watch_backups, self.watch_cronjobs, self.resync):
            threading.Thread(target=target, daemon=True).start()
        while True:
            time.sleep(3600)


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()  # local development
    Controller().run()


if __name__ == "__main__":
    main()
