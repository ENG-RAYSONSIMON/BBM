from django.db import models
from django.db.models.expressions import Expression, Value

from .tenancy import require_current_business_id


class CurrentBusinessId(Expression):
    """The active business id, resolved when the query is compiled to SQL.

    Resolving at execution rather than when the queryset is built keeps
    querysets declared at import time (e.g. a serializer field's
    `queryset=Role.objects.all()`) scoped to whichever business is active when
    they run, and still fails closed if none is.
    """

    def __init__(self):
        super().__init__(output_field=models.UUIDField())

    def as_sql(self, compiler, connection):
        value = Value(require_current_business_id(), output_field=models.UUIDField())
        return compiler.compile(value)


class TenantQuerySet(models.QuerySet):
    pass


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    def get_queryset(self):
        return super().get_queryset().filter(business_id=CurrentBusinessId())
