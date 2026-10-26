from .actor import reset_current_actor, set_current_actor
from .tenancy import reset_current_business_id, set_current_business_id


class TenantContextMiddleware:
    """Start each request with no active business or actor and clear them
    afterwards, so neither leaks into the next request served by the same
    worker thread."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = set_current_business_id(None)
        actor_token = set_current_actor(None)
        try:
            return self.get_response(request)
        finally:
            reset_current_actor(actor_token)
            reset_current_business_id(token)
