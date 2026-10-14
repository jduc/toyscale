"""The HTTP API: the door the UI (chapter 9) will knock on."""

import logging
from collections import Counter
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query

from . import config as cfg
from . import k8s
from .models import Analysis, Status
from .orchestrator import Orchestrator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

orchestrator = Orchestrator()


@asynccontextmanager
async def lifespan(_: FastAPI):
    k8s.connect()          # find cluster credentials
    orchestrator.start()   # start the reconcile loop in a background thread
    yield


app = FastAPI(title="ToyScale API", lifespan=lifespan)


@app.post("/analyses", status_code=202)
def run_analyses(count: int = Query(1, ge=1, le=50)) -> list[Analysis]:
    """Queue `count` new analyses. 202 Accepted = "noted, the work happens later"."""
    return [orchestrator.submit() for _ in range(count)]


@app.get("/analyses")
def list_analyses() -> list[Analysis]:
    return orchestrator.list()


@app.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: str) -> Analysis:
    if (analysis := orchestrator.get(analysis_id)) is None:
        raise HTTPException(404, "unknown analysis")
    return analysis


@app.get("/stats")
def stats() -> dict:
    counts = Counter(a.status for a in orchestrator.list())
    return {"max_running": cfg.MAX_RUNNING, **{s.value: counts.get(s, 0) for s in Status}}


@app.get("/healthz")
def healthz() -> dict:
    """Used by Kubernetes in chapter 6 to check the API is alive."""
    return {"ok": True}
