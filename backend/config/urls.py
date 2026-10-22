from django.urls import path
from portal import views
from portal.admin import control

urlpatterns = [
    path("staff/", control.urls),
    path("api/session/", views.session),
    path("api/login/", views.credentials),
    path("api/register/", views.credentials),
    path("api/logout/", views.signout),
    path("api/profile/", views.profile),
    path("api/preferences/", views.preferences),
    path("api/password/", views.password),
    path("api/feed/", views.feed),
]
