"""The orchestrator: the program that replaces YOU from chapter 4.

It is a RECONCILE LOOP, the same pattern every Kubernetes controller uses:

    forever:
        observe   what exists in the cluster right now
        compare   with what each analysis needs next
        act       create / delete objects to move one step forward

It never assumes its last action worked. It just looks again on the next tick.
"""

import logging
import threading
import time
import uuid

from . import config as cfg
from . import k8s
from .models import RUNNING, Analysis, Status, now

log = logging.getLogger("orchestrator")


class Orchestrator:
    def __init__(self) -> None:
        self.analyses: dict[str, Analysis] = {}  # insertion order = queue order
        self._lock = threading.Lock()  # the API threads and the loop thread share `analyses`

    # --- called by the API ---------------------------------------------------

    def submit(self) -> Analysis:
        analysis = Analysis(id=f"an-{uuid.uuid4().hex[:6]}")  # valid as a Kubernetes name
        with self._lock:
            self.analyses[analysis.id] = analysis
        log.info("%s queued", analysis.id)
        return analysis

    def list(self) -> list[Analysis]:
        with self._lock:
            return [a.model_copy(deep=True) for a in self.analyses.values()]

    def get(self, analysis_id: str) -> Analysis | None:
        with self._lock:
            found = self.analyses.get(analysis_id)
            return found.model_copy(deep=True) if found else None

    # --- the loop ------------------------------------------------------------

    def start(self) -> None:
        threading.Thread(target=self._run_forever, name="orchestrator", daemon=True).start()

    def _run_forever(self) -> None:
        while True:
            try:
                self.tick()
            except Exception:  # e.g. the cluster is unreachable: log, and try again next tick
                log.exception("tick failed")
            time.sleep(cfg.TICK_SECONDS)

    def tick(self) -> None:
        # 1. OBSERVE: two `kubectl get`-like calls for the whole namespace.
        jobs = k8s.job_states()
        pods = k8s.pods_by_step()

        with self._lock:
            for a in self.analyses.values():
                self._refresh_pod_info(a, pods)
                # 2. COMPARE + 3. ACT, one analysis at a time. If acting fails (e.g. the
                # namespace quota is full), only THIS analysis waits; it retries next tick.
                try:
                    if a.status == Status.QUEUED:
                        self._maybe_start(a)
                    elif a.status == Status.ALIGNING:
                        self._advance(a, jobs, step="align")
                    elif a.status == Status.CALLING:
                        self._advance(a, jobs, step="call")
                except Exception as exc:
                    log.warning("%s: %s, will retry", a.id, getattr(exc, "reason", exc))

    def _running_count(self) -> int:
        return sum(1 for a in self.analyses.values() if a.status in RUNNING)

    def _maybe_start(self, a: Analysis) -> None:
        """QUEUED -> ALIGNING, but only if one of the MAX_RUNNING slots is free."""
        if self._running_count() >= cfg.MAX_RUNNING:
            return  # stay queued; we'll look again next tick
        k8s.create_pvc(a.id)
        k8s.create_job(a.id, "align")
        a.status, a.started_at = Status.ALIGNING, now()
        log.info("%s started: created PVC + align Job", a.id)

    def _advance(self, a: Analysis, jobs: dict[str, str], step: str) -> None:
        """Look at the current step's Job and decide what comes next."""
        state = jobs.get(k8s.job_name(a.id, step), "active")

        if state == "active":
            return  # still running: nothing to do, look again next tick

        if state == "failed":
            a.status, a.finished_at = Status.FAILED, now()
            a.error = f"step {step} failed (Job gave up after its retries)"
            k8s.delete_pvc(a.id)
            log.warning("%s failed at %s", a.id, step)
            return

        # state == "complete"
        if step == "align":
            k8s.create_job(a.id, "call")  # the output dependency: only now may step 2 exist
            a.status = Status.CALLING
            log.info("%s align complete: created call Job", a.id)
        else:
            a.result = k8s.last_log_line(a.call.pod) if a.call.pod else None
            a.status, a.finished_at = Status.SUCCEEDED, now()
            # Clean up everything: Jobs + pods first, otherwise the PVC stays "Terminating".
            # (Failed analyses keep their Jobs for debugging; their ttl removes them later.)
            k8s.delete_jobs(a.id)
            k8s.delete_pvc(a.id)
            log.info("%s succeeded", a.id)

    @staticmethod
    def _refresh_pod_info(a: Analysis, pods: dict) -> None:
        for step in ("align", "call"):
            if info := pods.get((a.id, step)):
                step_info = getattr(a, step)
                step_info.pod, step_info.node, step_info.phase = info["pod"], info["node"], info["phase"]
