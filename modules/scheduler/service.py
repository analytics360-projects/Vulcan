"""Scheduler service — reimplements Skadi (C# Hangfire) with APScheduler"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from config import settings, logger

_scheduler: AsyncIOScheduler | None = None


def start_scheduler():
    global _scheduler
    _scheduler = AsyncIOScheduler()

    from modules.scheduler.jobs.parametros_busqueda import run as parametros_run
    from modules.scheduler.jobs.ping_bitacora import run as ping_run
    from modules.scheduler.jobs.disable_tablets import run as tablets_run
    from modules.scheduler.jobs.disable_carbyne import run as carbyne_run
    from modules.scheduler.jobs.omitir_en_captura import run as omitir_run

    _scheduler.add_job(parametros_run, IntervalTrigger(minutes=2), id="parametros_busqueda", name="Parametros Busqueda")
    _scheduler.add_job(ping_run, IntervalTrigger(minutes=10), id="ping_bitacora", name="Ping Bitacora")
    _scheduler.add_job(tablets_run, IntervalTrigger(minutes=59), id="disable_tablets", name="Disable Tablets")
    _scheduler.add_job(carbyne_run, IntervalTrigger(minutes=30), id="disable_carbyne", name="Disable Carbyne")
    _scheduler.add_job(omitir_run, IntervalTrigger(minutes=59), id="omitir_en_captura", name="Omitir En Captura")

    _scheduler.start()
    logger.info("Scheduler started with 5 jobs")


def stop_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown()
        logger.info("Scheduler stopped")


def get_scheduler():
    return _scheduler


def get_jobs_status():
    if not _scheduler:
        return {}
    return {
        job.id: {
            "name": job.name,
            "next_run": str(job.next_run_time) if job.next_run_time else None,
            "trigger": str(job.trigger),
        }
        for job in _scheduler.get_jobs()
    }
