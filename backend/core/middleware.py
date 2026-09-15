from .tenancy import reset_current_business_id, set_current_business_id


class TenantContextMiddleware:
    """Start each request with no active business and clear it afterwards, so
    a business activated during one request never leaks into the next request
    served by the same worker thread."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = set_current_business_id(None)
        try:
            return self.get_response(request)
        finally:
            reset_current_business_id(token)
