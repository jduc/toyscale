"""Everything that talks to the Kubernetes API.

The manifests below are the SAME objects you wrote by hand in
playground/pipeline-by-hand/ (pvc.yaml, job-align.yaml, job-call.yaml),
just built as Python dicts with the analysis id filled in.
"""

import json

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

from . import config as cfg

APP_LABEL = "toyscale"


def connect() -> None:
    """Find credentials: inside a pod use its ServiceAccount, otherwise ~/.kube/config."""
    try:
        config.load_incluster_config()  # chapter 6
    except config.ConfigException:
        config.load_kube_config()  # your Mac: same file kubectl uses


# --- manifests -------------------------------------------------------------

def pvc_name(analysis_id: str) -> str:
    return f"data-{analysis_id}"


def job_name(analysis_id: str, step: str) -> str:
    return f"{analysis_id}-{step}"


def pvc_manifest(analysis_id: str) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "PersistentVolumeClaim",
        "metadata": {
            "name": pvc_name(analysis_id),
            "labels": {"app": APP_LABEL, "analysis": analysis_id},
        },
        "spec": {
            "storageClassName": "standard",
            "accessModes": ["ReadWriteOnce"],
            "resources": {"requests": {"storage": "100Mi"}},
        },
    }


def worker_env(analysis_id: str, step: str) -> list[dict]:
    """Environment variables for a worker pod: this is how the worker gets its settings."""
    env = {
        "STEP": step,
        "ANALYSIS_ID": analysis_id,
        "DATA_DIR": "/data",
        "DURATION_MIN": cfg.WORKER_DURATION_MIN,
        "DURATION_MAX": cfg.WORKER_DURATION_MAX,
    }
    if cfg.KAFKA_BOOTSTRAP:  # chapter 8: tell the worker where to send its events
        env["KAFKA_BOOTSTRAP"] = cfg.KAFKA_BOOTSTRAP
        env["KAFKA_TOPIC"] = cfg.KAFKA_TOPIC
    return [{"name": k, "value": v} for k, v in env.items()]


def job_manifest(analysis_id: str, step: str) -> dict:
    labels = {"app": APP_LABEL, "analysis": analysis_id, "step": step}
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": job_name(analysis_id, step), "labels": labels},
        "spec": {
            "backoffLimit": 2,
            "activeDeadlineSeconds": 300,
            "ttlSecondsAfterFinished": 600,
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "restartPolicy": "Never",
                    "containers": [{
                        "name": "worker",
                        "image": cfg.WORKER_IMAGE,
                        "env": worker_env(analysis_id, step),
                        "volumeMounts": [{"name": "data", "mountPath": "/data"}],
                        "resources": {
                            "requests": {"cpu": "100m", "memory": "64Mi"},
                            "limits": {"memory": "128Mi"},
                        },
                    }],
                    "volumes": [{
                        "name": "data",
                        "persistentVolumeClaim": {"claimName": pvc_name(analysis_id)},
                    }],
                },
            },
        },
    }


# --- actions (what `kubectl apply` / `delete` did for you in chapter 4) ------

def _ignore(status: int, call, *args, **kwargs):
    """Run an API call, treating one HTTP status as 'fine'.

    409 = already exists, 404 = already gone. Ignoring them makes our actions
    IDEMPOTENT: safe to repeat, which is what a reconcile loop needs.
    """
    try:
        return call(*args, **kwargs)
    except ApiException as exc:
        if exc.status != status:
            raise


def create_pvc(analysis_id: str) -> None:
    _ignore(409, client.CoreV1Api().create_namespaced_persistent_volume_claim,
            cfg.NAMESPACE, pvc_manifest(analysis_id))


def create_job(analysis_id: str, step: str) -> None:
    _ignore(409, client.BatchV1Api().create_namespaced_job,
            cfg.NAMESPACE, job_manifest(analysis_id, step))


def delete_pvc(analysis_id: str) -> None:
    _ignore(404, client.CoreV1Api().delete_namespaced_persistent_volume_claim,
            pvc_name(analysis_id), cfg.NAMESPACE)


def delete_jobs(analysis_id: str) -> None:
    """Delete both Jobs AND their pods ("Background" = the pods are removed too).

    Needed because a PVC can't be deleted while any pod object, even a
    Completed one, still uses it (the `kubernetes.io/pvc-protection` finalizer).
    """
    for step in ("align", "call"):
        _ignore(404, client.BatchV1Api().delete_namespaced_job,
                job_name(analysis_id, step), cfg.NAMESPACE, propagation_policy="Background")


# --- observations (what `kubectl get` did for you) ---------------------------

def job_states() -> dict[str, str]:
    """{job name: "active" | "complete" | "failed"} for all our Jobs."""
    jobs = client.BatchV1Api().list_namespaced_job(
        cfg.NAMESPACE, label_selector=f"app={APP_LABEL}")
    states = {}
    for job in jobs.items:
        state = "active"
        for cond in job.status.conditions or []:
            # The same conditions `kubectl wait --for=condition=complete` looks at.
            if cond.status == "True" and cond.type in ("Complete", "Failed"):
                state = cond.type.lower()
        states[job.metadata.name] = state
    return states


def pods_by_step() -> dict[tuple[str, str], dict]:
    """{(analysis id, step): {pod, node, phase}} using the newest pod of each step."""
    pods = client.CoreV1Api().list_namespaced_pod(
        cfg.NAMESPACE, label_selector=f"app={APP_LABEL}")
    found = {}
    for pod in sorted(pods.items, key=lambda p: p.metadata.creation_timestamp):
        key = (pod.metadata.labels.get("analysis"), pod.metadata.labels.get("step"))
        found[key] = {"pod": pod.metadata.name, "node": pod.spec.node_name,
                      "phase": pod.status.phase}
    return found


def last_log_line(pod: str) -> dict | None:
    """The worker's final JSON line (`step.completed` ...), i.e. `kubectl logs --tail=1`."""
    try:
        text = client.CoreV1Api().read_namespaced_pod_log(pod, cfg.NAMESPACE, tail_lines=1)
        return json.loads(text)
    except (ApiException, ValueError):
        return None
