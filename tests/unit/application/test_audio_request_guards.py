import pytest
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import sleep

from app.application.audio_requests import AudioRequestRegistry
from app.application.errors import AudioIdempotencyConflict, AudioQuotaExceeded


def test_audio_quota_and_request_fingerprint():
    registry = AudioRequestRegistry(quota=1)
    first = registry.begin(4, "request-1", "fingerprint")
    registry.complete(first, {"ok": True})
    assert registry.begin(4, "request-1", "fingerprint").cached == {"ok": True}
    with pytest.raises(AudioIdempotencyConflict):
        registry.begin(4, "request-1", "different")
    with pytest.raises(AudioQuotaExceeded):
        registry.begin(4, "request-2", "other")


def test_failed_request_releases_idempotency_key_for_retry():
    registry = AudioRequestRegistry()
    lease = registry.begin(4, "request-1", "fingerprint")
    registry.release(lease)
    assert registry.begin(4, "request-1", "fingerprint").cached is None


def test_concurrent_duplicate_waits_for_and_reuses_successful_result():
    registry = AudioRequestRegistry()
    entered, resume = Event(), Event()
    def first():
        lease = registry.begin(7, "request-1", "fp")
        entered.set()
        assert resume.wait(timeout=2)
        registry.complete(lease, "cached")
        return "cached"
    def second():
        assert entered.wait(timeout=2)
        return registry.begin(7, "request-1", "fp").cached
    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(first)
        two = pool.submit(second)
        resume.set()
        assert one.result(timeout=2) == "cached"
        assert two.result(timeout=2) == "cached"


def test_successful_idempotency_entry_expires_after_ttl():
    registry = AudioRequestRegistry(ttl_seconds=0.01)
    lease = registry.begin(8, "request-1", "fp")
    registry.complete(lease, "cached")
    sleep(0.02)
    assert registry.begin(8, "request-1", "fp").cached is None
