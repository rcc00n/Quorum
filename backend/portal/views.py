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


def endpoint(methods, auth=False):
    def decorate(fn):
        @require_http_methods(methods)
        @wraps(fn)
        def wrapped(request):
            if auth and not request.user.is_authenticated:
                return response({"error": "Sign in to continue."}, 401)
            try:
                request.payload = json.loads(request.body or b"{}")
                if not isinstance(request.payload, dict):
                    raise ValueError()
            except (ValueError, UnicodeDecodeError):
                return response({"error": "Invalid JSON object."}, 400)
            return fn(request)

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


@endpoint(["GET", "POST"], auth=True)
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


@endpoint(["POST"], auth=True)
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


@endpoint(["POST"], auth=True)
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
        date.fromisoformat(day)
    except ValueError:
        return response({"error": "Use a date in YYYY-MM-DD format."}, 400)
    return response(adapter.snapshot(day, request.GET.get("topic", "")))
