from rest_framework.routers import SimpleRouter

from .views import NotificationViewSet

router = SimpleRouter()
router.register("notifications", NotificationViewSet, basename="notification")

app_name = "notifications"

urlpatterns = router.urls
