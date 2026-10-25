import hashlib
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from .models import AuthAttempt


def consume_attempt(request):
    # DECISION(2026-10-22, rcc00n/Codex): database-backed per-address limits. Why: shared across Gunicorn workers without provider calls.
    address = request.META.get("REMOTE_ADDR", "unknown")
    if not settings.DEBUG and address in ("127.0.0.1", "::1"):
        address = request.META.get("HTTP_X_REAL_IP", address)
    key = hashlib.sha256(address.encode()).hexdigest()
    now = timezone.now()
    with transaction.atomic():
        attempt, _ = AuthAttempt.objects.get_or_create(
            key=key, defaults={"started_at": now}
        )
        if now - attempt.started_at > timedelta(minutes=15):
            attempt.count, attempt.started_at = 0, now
        if attempt.count >= 20:
            return False
        attempt.count += 1
        attempt.save()
    return True


class StaffLoginLimit:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.method == "POST"
            and request.path == "/staff/login/"
            and not consume_attempt(request)
        ):
            response = HttpResponse(
                "Too many login attempts. Try again in 15 minutes.", status=429
            )
            response["Retry-After"] = "900"
            return response
        return self.get_response(request)
