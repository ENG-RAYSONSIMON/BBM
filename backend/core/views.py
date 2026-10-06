from django.db.models import ProtectedError
from rest_framework import status, viewsets
from rest_framework.exceptions import APIException


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This record is in use and cannot be deleted."
    default_code = "conflict"


class TenantModelViewSet(viewsets.ModelViewSet):
    """ModelViewSet for a TenantModel. Rows always come from the scoped
    `objects` manager, so another business's id is a plain 404 (NFR-7), and
    new rows get their business from the token via TenantModel.save().

    Deleting a row that other rows still reference (on_delete=PROTECT)
    answers 409 instead of 500.
    """

    model = None
    protected_message = Conflict.default_detail

    def get_queryset(self):
        return self.model.objects.all()

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError:
            raise Conflict(self.protected_message)
