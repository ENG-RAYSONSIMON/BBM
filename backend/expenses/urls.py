from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import ExpenseCategoryViewSet, ExpenseReceiptView, ExpensesSummaryView, ExpenseViewSet

router = SimpleRouter()
router.register("expenses", ExpenseViewSet, basename="expense")
router.register("expense-categories", ExpenseCategoryViewSet, basename="category")

app_name = "expenses"

urlpatterns = [
    # Before the router, so "summary" isn't read as an expense id.
    path("expenses/summary/", ExpensesSummaryView.as_view(), name="summary"),
    path("expenses/<uuid:pk>/receipt/", ExpenseReceiptView.as_view(), name="expense-receipt"),
    *router.urls,
]
