from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    """NFR-10: every list is paginated. `?page_size=` lets a client ask for
    up to 100 rows (e.g. to fill a dropdown)."""

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100
