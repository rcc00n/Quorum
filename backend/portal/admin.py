from django.contrib import admin
from django.contrib.auth.models import User, Group
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.template.response import TemplateResponse
from django.urls import path
from unfold.admin import ModelAdmin
from unfold.sites import UnfoldAdminSite
from .models import Preference
from .integration import adapter


class ControlSite(UnfoldAdminSite):
    site_header = "Quorum Control"
    site_title = "Quorum Control"
    index_template = "admin/control.html"
    login_template = "admin/control_login.html"

    def get_urls(self):
        return [
            path("topics/", self.admin_view(self.topics), name="topics"),
            path("sources/", self.admin_view(self.sources), name="sources"),
            path("status/", self.admin_view(self.status), name="status"),
            path(
                "integrations/", self.admin_view(self.integrations), name="integrations"
            ),
        ] + super().get_urls()

    def page(self, request, title, section):
        from .snapshot_store import SnapshotStore

        context = {
            **self.each_context(request),
            "title": title,
            "section": section,
            "operational": SnapshotStore().status(),
            "snapshot": adapter.snapshot(),
            "user_count": User.objects.count(),
            "preference_count": Preference.objects.count(),
        }
        return TemplateResponse(request, "admin/control.html", context)

    def index(self, request, extra_context=None):
        return self.page(request, "Overview", "overview")

    def topics(self, request):
        return self.page(request, "Topics", "topics")

    def sources(self, request):
        return self.page(request, "News sources", "sources")

    def status(self, request):
        return self.page(request, "System status", "status")

    def integrations(self, request):
        return self.page(request, "Integration readiness", "integrations")


control = ControlSite(name="control")


@admin.register(User, site=control)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser and (obj is None or obj.pk != request.user.pk)


@admin.register(Preference, site=control)
class PreferenceAdmin(ModelAdmin):
    list_display = ["user", "topics", "updated_at"]
    search_fields = ["user__username"]
    readonly_fields = ["user", "topics", "updated_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
