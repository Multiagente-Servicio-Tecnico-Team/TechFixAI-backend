"""Proceso local de cuota e idempotencia para envíos temporales de audio."""
from collections import defaultdict, deque
from dataclasses import dataclass
from hashlib import sha256
from threading import Condition, RLock
from time import monotonic
from typing import Any

from app.application.errors import AudioIdempotencyConflict, AudioQuotaExceeded


@dataclass(frozen=True)
class AudioRequestLease:
    key: tuple[int, str]
    fingerprint: str
    cached: Any = None


class AudioRequestRegistry:
    def __init__(self, *, quota: int = 5, window_seconds: float = 60, ttl_seconds: float = 600):
        self._quota = quota
        self._window = window_seconds
        self._ttl = ttl_seconds
        self._condition = Condition(RLock())
        self._records: dict[tuple[int, str], tuple[str, float, Any | None]] = {}
        self._in_progress: set[tuple[int, str]] = set()
        self._attempts: dict[int, deque[float]] = defaultdict(deque)

    @staticmethod
    def fingerprint(audio: bytes, *, duration_ms: int, pattern: str, conversation_id: str | None) -> str:
        digest = sha256()
        digest.update(audio)
        digest.update(f"\0{duration_ms}\0{pattern}\0{conversation_id or ''}".encode())
        return digest.hexdigest()

    def begin(self, customer_id: int, request_id: str, fingerprint: str) -> AudioRequestLease:
        key = (customer_id, request_id)
        with self._condition:
            while True:
                now = monotonic()
                self._purge(now)
                existing = self._records.get(key)
                if existing:
                    if existing[0] != fingerprint:
                        raise AudioIdempotencyConflict()
                    if existing[2] is not None:
                        return AudioRequestLease(key, fingerprint, existing[2])
                if key not in self._in_progress:
                    attempts = self._attempts[customer_id]
                    while attempts and attempts[0] <= now - self._window:
                        attempts.popleft()
                    if len(attempts) >= self._quota:
                        raise AudioQuotaExceeded()
                    attempts.append(now)
                    self._records[key] = (fingerprint, now + self._ttl, None)
                    self._in_progress.add(key)
                    return AudioRequestLease(key, fingerprint)
                self._condition.wait()

    def complete(self, lease: AudioRequestLease, result: Any) -> None:
        with self._condition:
            self._records[lease.key] = (lease.fingerprint, monotonic() + self._ttl, result)
            self._in_progress.discard(lease.key)
            self._condition.notify_all()

    def release(self, lease: AudioRequestLease) -> None:
        with self._condition:
            if self._records.get(lease.key, (None,))[0] == lease.fingerprint:
                self._records.pop(lease.key, None)
            self._in_progress.discard(lease.key)
            self._condition.notify_all()

    def _purge(self, now: float) -> None:
        for key, (_, expires, _) in tuple(self._records.items()):
            if expires <= now and key not in self._in_progress:
                self._records.pop(key, None)
