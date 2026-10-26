from accounts.rbac import FINANCE_VIEW

from .permissions import has_permission


class FinanceFieldsMixin:
    """Leave buying costs and profit out of the response unless the caller
    holds finance.view. Fails closed: without a request there is nothing to
    show them to."""

    finance_fields = ()  # field names

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not has_permission(self.context.get("request"), FINANCE_VIEW):
            for field in self.finance_fields:
                data.pop(field, None)
        return data
