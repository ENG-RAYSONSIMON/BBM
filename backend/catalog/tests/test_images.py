import io
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from PIL import Image

from catalog.models import Product

from .helpers import TenantAPITestCase, make_product

MEDIA = tempfile.mkdtemp(prefix="bbm-test-media-")


def image_file(fmt="PNG", size=(10, 10), name="photo.png"):
    buffer = io.BytesIO()
    Image.new("RGB", size, "pink").save(buffer, format=fmt)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


@override_settings(MEDIA_ROOT=MEDIA)
class ProductImageTests(TenantAPITestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        super().setUp()
        self.product = make_product(self.business_a)
        self.url = reverse("catalog:product-image", args=[self.product.pk])
        self.as_user(self.owner_a, self.business_a)

    def upload(self, file):
        return self.client.put(self.url, {"image": file}, format="multipart")

    def stored(self):
        return Product.all_objects.get(pk=self.product.pk).image

    def test_valid_image_is_stored_under_the_business_with_a_random_name(self):
        response = self.upload(image_file(name="../../evil.png"))

        self.assertEqual(response.status_code, 200, response.data)
        name = self.stored().name
        self.assertTrue(name.startswith(f"products/{self.business_a.pk}/"))
        self.assertTrue(name.endswith(".png"))
        self.assertNotIn("evil", name)
        self.assertIn(name, response.data["image"])

    def test_extension_follows_real_format_not_filename(self):
        response = self.upload(image_file(fmt="JPEG", name="photo.png"))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(self.stored().name.endswith(".jpg"))

    def test_replacing_deletes_the_old_file(self):
        self.upload(image_file())
        first = self.stored()
        storage, old_name = first.storage, first.name

        self.upload(image_file(fmt="WEBP", name="new.webp"))

        self.assertFalse(storage.exists(old_name))
        self.assertTrue(self.stored().name.endswith(".webp"))

    def test_delete_removes_image_and_file(self):
        self.upload(image_file())
        stored = self.stored()

        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["image"])
        self.assertFalse(stored.storage.exists(stored.name))

    def test_non_image_with_image_name_is_rejected(self):
        fake = SimpleUploadedFile("photo.png", b"<?php echo 'hi'; ?>", content_type="image/png")
        response = self.upload(fake)
        self.assertEqual(response.status_code, 400)
        self.assertIn("image", response.data)
        self.assertFalse(self.stored())

    def test_disallowed_format_is_rejected(self):
        response = self.upload(image_file(fmt="GIF", name="anim.gif"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("JPEG, PNG or WebP", str(response.data["image"]))

    @override_settings(PRODUCT_IMAGE_MAX_BYTES=100)
    def test_oversized_file_is_rejected(self):
        response = self.upload(image_file(size=(200, 200)))
        self.assertEqual(response.status_code, 400)
        self.assertIn("too large", str(response.data["image"]))

    def test_oversized_dimensions_are_rejected(self):
        response = self.upload(image_file(size=(4001, 1)))
        self.assertEqual(response.status_code, 400)
        self.assertIn("4000", str(response.data["image"]))

    def test_admin_can_upload(self):
        self.as_user(self.admin_a, self.business_a)
        self.assertEqual(self.upload(image_file()).status_code, 200)
