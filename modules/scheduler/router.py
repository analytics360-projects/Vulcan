"""Scheduler router"""
from fastapi import APIRouter, HTTPException
from config import logger

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


@router.get("/status")
async def scheduler_status():
    from modules.scheduler.service import get_jobs_status
    return {"jobs": get_jobs_status()}


@router.post("/trigger/{job_name}")
async def trigger_job(job_name: str):
    from modules.scheduler.service import get_scheduler
    sched = get_scheduler()
    if not sched:
        raise HTTPException(status_code=503, detail="Scheduler not running")
    job = sched.get_job(job_name)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_name}' not found")
    try:
        job.modify(next_run_time=None)  # Run immediately
        sched.wakeup()
        return {"triggered": job_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
