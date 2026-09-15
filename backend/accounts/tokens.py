from rest_framework_simplejwt.tokens import RefreshToken

from core.tenancy import TENANT_CLAIM


def tokens_for(user, business):
    """Issue a refresh/access pair bound to one business.

    Access tokens copy the business_id claim from the refresh token, and
    refresh rotation keeps it.
    """
    refresh = RefreshToken.for_user(user)
    refresh[TENANT_CLAIM] = str(business.pk)
    return {"refresh": str(refresh), "access": str(refresh.access_token)}
