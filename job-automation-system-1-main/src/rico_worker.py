"""Redis-backed worker runtime for Rico AI.

Supports background reminders, ranking adaptation, opportunity detection,
Telegram callback processing, and autonomous scheduling.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

from redis import Redis
from rq import Queue, Worker

from src import rico_tasks

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rico_worker")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
QUEUE_NAME = os.getenv("RICO_QUEUE", "rico")


def redis_connection() -> Redis:
    return Redis.from_url(REDIS_URL)


def queue() -> Queue:
    return Queue(QUEUE_NAME, connection=redis_connection())


def enqueue(func: Callable[..., Any], *args: Any, **kwargs: Any):
    q = queue()
    return q.enqueue(func, *args, **kwargs)


def enqueue_daily_pipeline():
    return enqueue(rico_tasks.run_daily_pipeline_task)


def enqueue_weekly_report():
    return enqueue(rico_tasks.send_weekly_report_task)


def enqueue_followup_check(days_after_apply: int = 14):
    return enqueue(rico_tasks.check_followups_task, days_after_apply)


def enqueue_ranking_adaptation(user_id: str = "default"):
    return enqueue(rico_tasks.adapt_rankings_task, user_id)


def enqueue_opportunity_detection(user_id: str = "default"):
    return enqueue(rico_tasks.detect_opportunities_task, user_id)


def enqueue_telegram_update(update: dict):
    return enqueue(rico_tasks.process_telegram_action_task, update)


def start_worker() -> None:
    logger.info("rico_worker_starting")
    worker = Worker([QUEUE_NAME], connection=redis_connection())
    worker.work()


if __name__ == "__main__":
    start_worker()
