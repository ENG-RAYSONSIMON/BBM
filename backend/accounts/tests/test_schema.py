import importlib

from django.test import SimpleTestCase, override_settings
from django.urls import clear_url_caches
from drf_spectacular.drainage import GENERATOR_STATS
from drf_spectacular.generators import SchemaGenerator

import config.urls


def reload_urls():
    clear_url_caches()
    importlib.reload(config.urls)


class SchemaTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        GENERATOR_STATS.reset()
        with GENERATOR_STATS.silence():
            cls.schema = SchemaGenerator().get_schema(request=None, public=True)
        cls.warnings = dict(GENERATOR_STATS._warn_cache)
        cls.errors = dict(GENERATOR_STATS._error_cache)
        GENERATOR_STATS.reset()

    def test_schema_has_no_errors_or_warnings(self):
        self.assertEqual(self.errors, {})
        self.assertEqual(self.warnings, {})

    def test_bearer_auth_is_documented(self):
        self.assertIn("jwtAuth", self.schema["components"]["securitySchemes"])
        me = self.schema["paths"]["/api/v1/auth/me/"]["get"]
        self.assertEqual(me["security"], [{"jwtAuth": []}])

    def test_public_endpoints_need_no_auth(self):
        login = self.schema["paths"]["/api/v1/auth/login/"]["post"]
        self.assertNotIn({"jwtAuth": []}, login.get("security", []))

    def test_required_permissions_are_documented(self):
        settings_ops = self.schema["paths"]["/api/v1/settings/"]
        self.assertEqual(settings_ops["get"]["x-required-permissions"], ["settings.view"])
        self.assertEqual(settings_ops["patch"]["x-required-permissions"], ["settings.manage"])
        self.assertIn("`settings.manage`", settings_ops["patch"]["description"])
        self.assertNotIn("x-required-permissions", self.schema["paths"]["/api/v1/auth/me/"]["get"])

    def test_auth_payload_response_is_documented(self):
        login = self.schema["paths"]["/api/v1/auth/login/"]["post"]
        ref = login["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        self.assertEqual(ref, "#/components/schemas/AuthPayload")


class DocsRoutingTests(SimpleTestCase):
    def tearDown(self):
        reload_urls()  # back to the urlconf for the test-run settings

    def test_docs_are_not_routed_without_debug(self):
        with override_settings(DEBUG=False):
            reload_urls()
            for url in ("/api/schema/", "/api/docs/", "/api/redoc/"):
                self.assertEqual(self.client.get(url).status_code, 404, url)

    def test_docs_are_routed_with_debug(self):
        with override_settings(DEBUG=True):
            reload_urls()
            for url in ("/api/schema/", "/api/docs/", "/api/redoc/"):
                self.assertEqual(self.client.get(url).status_code, 200, url)
            response = self.client.get("/api/schema/", HTTP_AUTHORIZATION="Bearer stale")
            self.assertEqual(response.status_code, 200)
