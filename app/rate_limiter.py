from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from fastapi import Request

from app.db import get_connection


ASK_SITE_DAILY_LIMIT = 30
ASK_IP_DAILY_LIMIT = 15
ASK_IP_MINUTE_LIMIT = 5
UPLOAD_SITE_DAILY_LIMIT = 10
UPLOAD_IP_DAILY_LIMIT = 3
GEMINI_ADVISORY_LOCK_ID = 824_731_905


@contextmanager
def gemini_slot() -> Iterator[bool]:
    connection = get_connection()
    connection.autocommit = True
    acquired = False

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_try_advisory_lock(%s);",
                (GEMINI_ADVISORY_LOCK_ID,),
            )
            result = cursor.fetchone()
            acquired = bool(result and result[0])

        yield acquired
    finally:
        if acquired:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT pg_advisory_unlock(%s);",
                        (GEMINI_ADVISORY_LOCK_ID,),
                    )
            except Exception:
                pass

        connection.close()


@dataclass(frozen=True)
class RateLimitRule:
    scope: str
    client_key: str
    window_start: datetime
    limit: int
    retry_after: int
    message: str


class RateLimitExceeded(Exception):
    def __init__(self, message: str, retry_after: int) -> None:
        super().__init__(message)
        self.message = message
        self.retry_after = retry_after


def get_client_key(request: Request) -> str:
    client_ip = request.headers.get("cf-connecting-ip")

    if not client_ip:
        forwarded_for = request.headers.get("x-forwarded-for")

        if forwarded_for:
            client_ip = forwarded_for.split(",")[-1].strip()

    if not client_ip and request.client:
        client_ip = request.client.host

    normalized_ip = (client_ip or "unknown").strip().lower()
    return sha256(normalized_ip.encode("utf-8")).hexdigest()


def consume_ask_limit(client_key: str) -> None:
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    minute_start = now.replace(second=0, microsecond=0)

    rules = [
        RateLimitRule(
            scope="site_day",
            client_key="site",
            window_start=day_start,
            limit=ASK_SITE_DAILY_LIMIT,
            retry_after=_seconds_until(day_start + timedelta(days=1), now),
            message="The site has reached its daily question limit",
        ),
        RateLimitRule(
            scope="ip_day",
            client_key=client_key,
            window_start=day_start,
            limit=ASK_IP_DAILY_LIMIT,
            retry_after=_seconds_until(day_start + timedelta(days=1), now),
            message="You have reached your daily question limit",
        ),
        RateLimitRule(
            scope="ip_minute",
            client_key=client_key,
            window_start=minute_start,
            limit=ASK_IP_MINUTE_LIMIT,
            retry_after=_seconds_until(minute_start + timedelta(minutes=1), now),
            message="You have reached the question limit for this minute",
        ),
    ]

    _consume_rules(action="ask", rules=rules)


def consume_upload_limit(client_key: str) -> None:
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    retry_after = _seconds_until(day_start + timedelta(days=1), now)

    rules = [
        RateLimitRule(
            scope="site_day",
            client_key="site",
            window_start=day_start,
            limit=UPLOAD_SITE_DAILY_LIMIT,
            retry_after=retry_after,
            message="The site has reached its daily upload limit",
        ),
        RateLimitRule(
            scope="ip_day",
            client_key=client_key,
            window_start=day_start,
            limit=UPLOAD_IP_DAILY_LIMIT,
            retry_after=retry_after,
            message="You have reached your daily upload limit",
        ),
    ]

    _consume_rules(action="upload", rules=rules)


def _consume_rules(action: str, rules: list[RateLimitRule]) -> None:
    query = """
        INSERT INTO rate_limit_counters (
            action,
            scope,
            client_key,
            window_start,
            request_count
        )
        VALUES (%s, %s, %s, %s, 1)
        ON CONFLICT (action, scope, client_key, window_start)
        DO UPDATE
        SET request_count = rate_limit_counters.request_count + 1
        WHERE rate_limit_counters.request_count < %s
        RETURNING request_count;
    """

    with get_connection() as connection:
        with connection.cursor() as cursor:
            for rule in rules:
                cursor.execute(
                    query,
                    (
                        action,
                        rule.scope,
                        rule.client_key,
                        rule.window_start,
                        rule.limit,
                    ),
                )

                if cursor.fetchone() is None:
                    raise RateLimitExceeded(
                        message=rule.message,
                        retry_after=rule.retry_after,
                    )

            cursor.execute(
                """
                DELETE FROM rate_limit_counters
                WHERE window_start < %s;
                """,
                (datetime.now(timezone.utc) - timedelta(days=2),),
            )


def _seconds_until(end: datetime, now: datetime) -> int:
    return max(1, int((end - now).total_seconds()) + 1)
