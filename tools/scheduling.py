"""@tool set_alarm, schedule_reminder, list_reminders, cancel_reminder.

Uses a single shared BackgroundScheduler so alarms/reminders can speak
through the same TTS + speakers the voice loop uses. Import `scheduler`
and call `.start()` once from run_voice.py — these @tool functions
assume it's already running.
"""

from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from langchain_core.tools import tool

from voice.audio_utils import play_pcm
from voice.tts import SAMPLE_RATE, synthesize_speech

scheduler = BackgroundScheduler()


def _announce(label: str) -> None:
    play_pcm(synthesize_speech(f"Reminder: {label}"), SAMPLE_RATE)


@tool
def set_alarm(hour: int, minute: int, label: str = "Alarm") -> str:
    """Set a daily recurring alarm.

    Args:
        hour: Hour in 24-hour format (0-23)
        minute: Minute (0-59)
        label: What to announce when it fires
    """
    job_id = f"alarm-{hour:02d}{minute:02d}-{label}"
    scheduler.add_job(
        _announce, trigger="cron", hour=hour, minute=minute, args=[label], id=job_id, replace_existing=True
    )
    return f"Alarm set for {hour:02d}:{minute:02d} daily — {label}"


@tool
def schedule_reminder(when: str, message: str) -> str:
    """Schedule a one-time reminder.

    Args:
        when: ISO 8601 datetime, e.g. "2026-09-10T14:30:00"
        message: What to announce
    """
    run_date = datetime.fromisoformat(when)
    job_id = f"reminder-{run_date.isoformat()}-{message[:20]}"
    scheduler.add_job(_announce, trigger="date", run_date=run_date, args=[message], id=job_id, replace_existing=True)
    return f"Reminder set for {run_date.isoformat()} — {message}"


@tool
def list_reminders() -> str:
    """List all upcoming alarms and reminders."""
    jobs = scheduler.get_jobs()
    if not jobs:
        return "No upcoming alarms or reminders."
    lines = [f"- {job.id}: next run {job.next_run_time}" for job in jobs]
    return "\n".join(lines)


@tool
def cancel_reminder(job_id: str) -> str:
    """Cancel an alarm or reminder by its ID (see list_reminders for IDs)."""
    scheduler.remove_job(job_id)
    return f"Cancelled: {job_id}"
