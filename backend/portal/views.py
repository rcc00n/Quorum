import json
from datetime import date
from functools import wraps
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.forms import UserCreationForm, PasswordChangeForm
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.http import require_http_methods
from .models import Preference
from .limits import consume_attempt
from .integration import adapter


def response(data, status=200):
    r = JsonResponse(data, status=status)
    r["Cache-Control"] = "no-store"
    return r


PUBLIC_DEMO_GROUP = "Quorum public demo"


def endpoint(methods, auth=False, writable=False):
    def decorate(fn):
        @require_http_methods(methods)
        @wraps(fn)
        def wrapped(request, *args, **kwargs):
            if auth and not request.user.is_authenticated:
                return response({"error": "Sign in to continue."}, 401)
            # DECISION(2026-10-27, rcc00n/Codex): the deliberately public demo may read, sign in and
            # sign out, but cannot edit its shared account/topics. Why: visitors must not lock each other out.
            if writable and request.method != "GET" and request.user.groups.filter(name=PUBLIC_DEMO_GROUP).exists():
                return response({"error": "The public demo account is read-only. Create your own account to change profile, password or topics."}, 403)
            try:
                request.payload = json.loads(request.body or b"{}")
                if not isinstance(request.payload, dict):
                    raise ValueError()
            except (ValueError, UnicodeDecodeError):
                return response({"error": "Invalid JSON object."}, 400)
            return fn(request, *args, **kwargs)

        return wrapped

    return decorate


def user_data(user):
    pref, _ = Preference.objects.get_or_create(user=user)
    return {
        "username": user.username,
        "name": user.first_name,
        "email": user.email,
        "topics": pref.topics,
        "is_staff": user.is_staff,
    }


@endpoint(["GET"])
def session(request):
    return response(
        {
            "csrfToken": get_token(request),
            "user": user_data(request.user) if request.user.is_authenticated else None,
        }
    )


@endpoint(["POST"])
def credentials(request):
    data = request.payload
    if any(
        not isinstance(data.get(k), str) or len(data[k]) > 256
        for k in ("username", "password")
    ):
        return response({"error": "Enter a username and password."}, 400)
    if not consume_attempt(request):
        return response({"error": "Too many attempts. Try again in 15 minutes."}, 429)
    if request.path.endswith("register/"):
        form = UserCreationForm(
            {
                "username": data.get("username"),
                "password1": data.get("password"),
                "password2": data.get("password"),
            }
        )
        if not form.is_valid():
            return response(
                {
                    "error": " ".join(
                        str(e) for errors in form.errors.values() for e in errors
                    )
                },
                400,
            )
        user = form.save()
    else:
        user = authenticate(
            request, username=data.get("username"), password=data.get("password")
        )
        if user is None:
            return response({"error": "Username or password is incorrect."}, 400)
    login(request, user)
    return response({"user": user_data(user), "csrfToken": get_token(request)})


@endpoint(["POST"], auth=True)
def signout(request):
    logout(request)
    return response({"ok": True})


@endpoint(["GET", "POST"], auth=True, writable=True)
def profile(request):
    if request.method == "POST":
        data = request.payload
        name, email = data.get("name", ""), data.get("email", "")
        from django.core.validators import validate_email
        from django.core.exceptions import ValidationError

        if not isinstance(name, str) or not isinstance(email, str) or len(name) > 150:
            return response({"error": "Invalid profile."}, 400)
        try:
            if email:
                validate_email(email)
        except ValidationError:
            return response({"error": "Enter a valid email address."}, 400)
        request.user.first_name, request.user.email = name, email
        request.user.save(update_fields=["first_name", "email"])
    return response({"user": user_data(request.user)})


@endpoint(["POST"], auth=True, writable=True)
def preferences(request):
    topics = request.payload.get("topics")
    allowed = {t["id"] for t in adapter.snapshot()["topics"]}
    if (
        not isinstance(topics, list)
        or len(topics) > 30
        or any(not isinstance(t, str) or t not in allowed for t in topics)
    ):
        return response({"error": "Choose topics from the available catalog."}, 400)
    Preference.objects.update_or_create(
        user=request.user, defaults={"topics": list(dict.fromkeys(topics))}
    )
    return response({"user": user_data(request.user)})


@endpoint(["POST"], auth=True, writable=True)
def password(request):
    form = PasswordChangeForm(request.user, request.payload)
    if not form.is_valid():
        return response(
            {
                "error": " ".join(
                    str(e) for errors in form.errors.values() for e in errors
                )
            },
            400,
        )
    update_session_auth_hash(request, form.save())
    return response({"ok": True})


@endpoint(["GET"], auth=True)
def feed(request):
    day = request.GET.get("date", date.today().isoformat())
    try:
        if date.fromisoformat(day).isoformat() != day:
            raise ValueError()
    except ValueError:
        return response({"error": "Use a date in YYYY-MM-DD format."}, 400)
    revision = request.GET.get("revision")
    if revision:
        import re

        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", revision):
            return response({"error": "Invalid revision identifier."}, 400)
    return response(
        adapter.snapshot(day, request.GET.get("topic", ""), revision=revision)
    )


@endpoint(["GET"], auth=True)
def event_detail(request, event_id):
    day = request.GET.get("date", "")
    if day:
        try:
            if date.fromisoformat(day).isoformat() != day:
                raise ValueError()
        except ValueError:
            return response({"error": "Use a date in YYYY-MM-DD format."}, 400)
    revision = request.GET.get("revision")
    import re

    if revision and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", revision):
        return response({"error": "Invalid revision identifier."}, 400)
    return response(adapter.event(event_id, day, revision))


@endpoint(["GET"])
def reasoning_preview(request):
    """Explicit opt-in loopback development fixture; never a production data source."""
    import os
    from django.conf import settings
    from .reasoning_preview import load_preview
    from .snapshot_validation import SnapshotError

    if not (
        settings.DEBUG
        and os.getenv("QUORUM_ENABLE_REASONING_PREVIEW") == "1"
        and request.get_host().split(":")[0] in ("localhost", "127.0.0.1")
        and not settings.DATA_DIR.resolve().is_relative_to("/var/lib/quorum")
    ):
        return response({"error": "Not found."}, 404)
    if not request.user.is_authenticated:
        return response({"error": "Sign in to preview."}, 401)
    try:
        snapshot = load_preview(os.getenv("QUORUM_REASONING_PREVIEW_FILE"))
        if (
            request.GET.get("date")
            and request.GET["date"] != snapshot["reasoning"]["edition_date"]
        ):
            return response({"error": "This preview edition is unavailable."}, 404)
        if request.GET.get("version") and request.GET["version"] != str(
            snapshot["reasoning"]["version"]
        ):
            return response({"error": "This preview version is unavailable."}, 404)
        return response(snapshot)
    except (SnapshotError, OSError, ValueError, TypeError):
        return response(
            {
                "error": "Reasoning preview unavailable: input failed compatibility checks."
            },
            422,
        )
