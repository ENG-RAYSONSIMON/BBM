from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from accounts.services import get_active_membership

from .tenancy import TENANT_CLAIM, set_current_business_id


class TenantJWTAuthentication(JWTAuthentication):
    """JWT authentication that also activates the token's business.

    The business comes only from the signed `business_id` claim and must match
    an active membership, so a client cannot pick a tenant per request.
    """

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None

        user, validated_token = result
        membership = get_active_membership(user.pk, validated_token.get(TENANT_CLAIM))
        if membership is None:
            raise AuthenticationFailed(
                _("No active business membership for this token."),
                code="no_active_membership",
            )

        request.business = membership.business
        request.membership = membership
        set_current_business_id(membership.business_id)
        return user, validated_token
