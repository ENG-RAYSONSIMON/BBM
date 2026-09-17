from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm

from core.admin import TenantModelAdmin

from .models import (
    Business,
    BusinessSettings,
    Permission,
    PasswordResetToken,
    Role,
    RolePermission,
    User,
    UserRole,
)


class EmailUserCreationForm(AdminUserCreationForm):
    class Meta(AdminUserCreationForm.Meta):
        model = User
        fields = ("email",)


class EmailUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    form = EmailUserChangeForm
    add_form = EmailUserCreationForm
    ordering = ("email",)
    list_display = ("email", "first_name", "last_name", "is_active", "is_staff")
    search_fields = ("email", "first_name", "last_name", "phone")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "phone")}),
        (
            "Permissions",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "usable_password", "password1", "password2"),
            },
        ),
    )


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ("name", "currency", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "tin", "email", "phone")


@admin.register(Role)
class RoleAdmin(TenantModelAdmin):
    list_display = ("name", "business", "is_system")


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    """The catalog is maintained in accounts.rbac plus data migrations."""

    list_display = ("codename", "description")
    search_fields = ("codename",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RolePermission)
class RolePermissionAdmin(TenantModelAdmin):
    list_display = ("role", "permission", "business")
    list_select_related = ("role", "permission", "business")


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "expires_at", "used_at")
    readonly_fields = ("user", "token_hash", "expires_at", "used_at")

    def has_add_permission(self, request):
        return False


@admin.register(UserRole)
class UserRoleAdmin(TenantModelAdmin):
    list_display = ("user", "business", "role", "is_active")
    list_select_related = ("user", "business", "role")


@admin.register(BusinessSettings)
class BusinessSettingsAdmin(TenantModelAdmin):
    list_display = ("business", "low_stock_threshold", "expiry_warning_days", "tax_rate")
