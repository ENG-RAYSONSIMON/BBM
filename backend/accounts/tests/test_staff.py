"""Staff management: adding people with a temporary password, the forced
first-login change, who may give which role, turning access off, and
password resets. Ids are membership ids, so another business's are 404."""

from django.urls import reverse

from accounts.models import Role, User, UserRole
from audit.models import AuditLog
from catalog.tests.helpers import PASSWORD, TenantAPITestCase, make_member
from core.tenancy import tenant_context

STAFF_URL = reverse("accounts:staff-list")
ROLES_URL = reverse("accounts:role-list")
LOGIN_URL = reverse("accounts:login")
REFRESH_URL = reverse("accounts:refresh")
ME_URL = reverse("accounts:me")
CHANGE_URL = reverse("accounts:change-password")
PRODUCTS_URL = reverse("catalog:product-list")
TEMP = "Muda-wa-2026!"
NEW = "Neno-Langu-77!"


def detail_url(pk):
    return reverse("accounts:staff-detail", args=[pk])


def reset_url(pk):
    return reverse("accounts:staff-reset-password", args=[pk])


class StaffTestCase(TenantAPITestCase):
    def setUp(self):
        super().setUp()
        with tenant_context(self.business_a):
            self.roles = {r.name: r for r in Role.objects.all()}
        self.as_user(self.owner_a, self.business_a)

    def add(self, email="neema@example.com", role=Role.SELLER, **extra):
        payload = {"email": email, "first_name": "Neema", "role": str(self.roles[role].pk), "temp_password": TEMP}
        return self.client.post(STAFF_URL, {**payload, **extra}, format="json")

    def membership(self, user, business=None):
        return UserRole.all_objects.get(user=user, business=business or self.business_a)

    def login(self, email, password):
        self.client.credentials()
        return self.client.post(LOGIN_URL, {"email": email, "password": password}, format="json")

    def use(self, payload):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {payload['access']}")

    def can_refresh(self, payload):
        self.client.credentials()
        return self.client.post(REFRESH_URL, {"refresh": payload["refresh"]}, format="json").status_code == 200


class AddStaffTests(StaffTestCase):
    def test_new_person_gets_a_temporary_password_and_must_change_it(self):
        response = self.add()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["role_name"], Role.SELLER)
        self.assertTrue(response.data["must_change_password"])
        self.assertTrue(response.data["can_manage"])

        login = self.login("neema@example.com", TEMP)
        self.assertEqual(login.status_code, 200)
        self.assertTrue(login.data["user"]["must_change_password"])
        self.assertEqual(login.data["role"], Role.SELLER)

        self.use(login.data)
        locked = self.client.get(PRODUCTS_URL)
        self.assertEqual(locked.status_code, 403)
        self.assertEqual(locked.data["detail"].code, "password_change_required")
        self.assertEqual(self.client.get(ME_URL).status_code, 200)

        changed = self.client.post(CHANGE_URL, {"current_password": TEMP, "new_password": NEW}, format="json")
        self.assertEqual(changed.status_code, 200, changed.data)
        self.assertFalse(changed.data["user"]["must_change_password"])
        self.use(changed.data)
        self.assertEqual(self.client.get(PRODUCTS_URL).status_code, 200)
        # The temporary password's session is over; the new one works.
        self.assertFalse(self.can_refresh(login.data))
        self.assertTrue(self.can_refresh(changed.data))
        self.assertEqual(self.login("neema@example.com", NEW).status_code, 200)

    def test_an_existing_account_cannot_be_added(self):
        # Shop B makes an account for an email and knows its password...
        with tenant_context(self.business_b):
            self.roles["b-seller"] = Role.objects.get(name=Role.SELLER)
        self.as_user(self.owner_b, self.business_b)
        self.assertEqual(self.add(email="neema@example.com", role="b-seller").status_code, 201)
        # ...so shop A must not be able to attach that account: B could log in here.
        self.as_user(self.owner_a, self.business_a)
        response = self.add(email="Neema@example.com")
        self.assertIn("email", response.data)
        self.assertFalse(UserRole.all_objects.filter(user__email="neema@example.com", business=self.business_a).exists())
        self.assertIn("email", self.add(email="b@example.com").data)

    def test_validation(self):
        self.assertIn("temp_password", self.add(temp_password="").data)
        self.assertIn("temp_password", self.add(temp_password="123").data)
        self.assertIn("email", self.add(email="admin-a@example.com").data)
        with tenant_context(self.business_b):
            other_role = Role.objects.get(name=Role.SELLER)
        self.roles["other"] = other_role
        self.assertIn("role", self.add(role="other").data)
        self.assertFalse(User.objects.filter(email="neema@example.com").exists())

    def test_audit_entries(self):
        pk = self.add().data["id"]
        self.client.patch(detail_url(pk), {"role": str(self.roles[Role.CASHIER].pk)}, format="json")
        self.client.post(reset_url(pk), {"temp_password": TEMP + "x"}, format="json")
        actions = list(
            AuditLog.all_objects.filter(business=self.business_a, target_id=pk)
            .order_by("created_at")
            .values_list("action", "changes")
        )
        self.assertEqual([a for a, _ in actions], ["STAFF_ADD", "STAFF_CHANGE", "STAFF_PASSWORD_RESET"])
        self.assertEqual(actions[1][1], {"role": [Role.SELLER, Role.CASHIER]})


class RoleRuleTests(StaffTestCase):
    def test_roles_list_marks_what_you_may_give(self):
        owner_view = {r["name"]: r["assignable"] for r in self.client.get(ROLES_URL).data}
        self.assertEqual(
            owner_view, {Role.ADMIN: True, Role.CASHIER: True, Role.OWNER: False, Role.SELLER: True}
        )
        self.as_user(self.admin_a, self.business_a)
        admin_view = {r["name"]: r["assignable"] for r in self.client.get(ROLES_URL).data}
        self.assertEqual(
            admin_view, {Role.ADMIN: False, Role.CASHIER: True, Role.OWNER: False, Role.SELLER: True}
        )

    def test_admin_adds_sellers_but_not_admins_or_owners(self):
        self.as_user(self.admin_a, self.business_a)
        self.assertEqual(self.add(role=Role.CASHIER).status_code, 201)
        self.assertIn("role", self.add(email="x@example.com", role=Role.ADMIN).data)
        self.assertIn("role", self.add(email="y@example.com", role=Role.OWNER).data)

    def test_nobody_changes_themselves_or_the_owner(self):
        owner = self.membership(self.owner_a)
        response = self.client.patch(detail_url(owner.pk), {"is_active": False}, format="json")
        self.assertEqual(response.status_code, 400)  # the owner's own row

        self.as_user(self.admin_a, self.business_a)
        for pk in (owner.pk, self.membership(self.admin_a).pk):
            with self.subTest(pk=pk):
                self.assertEqual(self.client.patch(detail_url(pk), {"is_active": False}, format="json").status_code, 400)
                self.assertEqual(self.client.post(reset_url(pk), {"temp_password": TEMP}, format="json").status_code, 400)
        rows = {r["email"]: r["can_manage"] for r in self.client.get(STAFF_URL).data["results"]}
        self.assertEqual(rows, {"a@example.com": False, "admin-a@example.com": False})
        self.assertTrue(self.membership(self.owner_a).is_active)

    def test_owner_cannot_be_given_by_promotion(self):
        pk = self.add().data["id"]
        response = self.client.patch(detail_url(pk), {"role": str(self.roles[Role.OWNER].pk)}, format="json")
        self.assertIn("role", response.data)

    def test_needs_staff_manage(self):
        seller = make_member(self.business_a, "seller@example.com", Role.SELLER)
        self.as_user(seller, self.business_a)
        self.assertEqual(self.client.get(STAFF_URL).status_code, 403)
        self.assertEqual(self.client.get(ROLES_URL).status_code, 403)
        self.assertEqual(self.add(email="z@example.com").status_code, 403)


class AccessTests(StaffTestCase):
    def setUp(self):
        super().setUp()
        self.pk = self.add().data["id"]
        self.neema = User.objects.get(email="neema@example.com")
        self.neema.must_change_password = False
        self.neema.save()

    def test_turning_access_off_works_on_the_next_request(self):
        session = self.login("neema@example.com", TEMP).data
        response = self.client.patch(detail_url(self.pk), {"is_active": False}, format="json")
        self.assertEqual(response.status_code, 401)  # logged out as the owner above
        self.as_user(self.owner_a, self.business_a)
        self.assertEqual(self.client.patch(detail_url(self.pk), {"is_active": False}, format="json").status_code, 200)

        self.use(session)
        self.assertEqual(self.client.get(PRODUCTS_URL).status_code, 401)
        self.assertEqual(self.login("neema@example.com", TEMP).status_code, 401)

        self.as_user(self.owner_a, self.business_a)
        self.client.patch(detail_url(self.pk), {"is_active": True}, format="json")
        self.assertEqual(self.login("neema@example.com", TEMP).status_code, 200)

    def test_reset_password_ends_sessions_and_forces_a_change(self):
        session = self.login("neema@example.com", TEMP).data
        self.as_user(self.owner_a, self.business_a)
        self.assertEqual(self.client.post(reset_url(self.pk), {"temp_password": "Mpya-Kabisa-55!"}, format="json").status_code, 204)
        self.assertFalse(self.can_refresh(session))
        login = self.login("neema@example.com", "Mpya-Kabisa-55!")
        self.assertTrue(login.data["user"]["must_change_password"])

    def test_reset_refused_for_an_account_used_elsewhere(self):
        # Only Django admin can give one account several businesses.
        with tenant_context(self.business_a):
            pk = UserRole.objects.create(user=self.owner_b, role=self.roles[Role.SELLER]).pk
        response = self.client.post(reset_url(pk), {"temp_password": TEMP}, format="json")
        self.assertEqual(response.status_code, 400)
        self.owner_b.refresh_from_db()
        self.assertTrue(self.owner_b.check_password(PASSWORD))

    def test_platform_operators_are_left_to_django_admin(self):
        self.neema.is_staff = True
        self.neema.save()
        self.assertEqual(self.client.post(reset_url(self.pk), {"temp_password": TEMP}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(detail_url(self.pk), {"is_active": False}, format="json").status_code, 400)

    def test_change_password_checks_the_current_one(self):
        self.use(self.login("neema@example.com", TEMP).data)
        wrong = self.client.post(CHANGE_URL, {"current_password": "nope", "new_password": NEW}, format="json")
        self.assertIn("current_password", wrong.data)
        weak = self.client.post(CHANGE_URL, {"current_password": TEMP, "new_password": "123"}, format="json")
        self.assertIn("new_password", weak.data)
        same = self.client.post(CHANGE_URL, {"current_password": TEMP, "new_password": TEMP}, format="json")
        self.assertIn("new_password", same.data)

    def test_last_login_is_shown(self):
        self.login("neema@example.com", TEMP)
        self.as_user(self.owner_a, self.business_a)
        self.assertIsNotNone(self.client.get(detail_url(self.pk)).data["last_login"])


class IsolationTests(StaffTestCase):
    def test_another_business_cannot_see_or_change_staff(self):
        pk = self.add().data["id"]
        self.as_user(self.owner_b, self.business_b)
        self.assertEqual(self.client.get(detail_url(pk)).status_code, 404)
        self.assertEqual(self.client.patch(detail_url(pk), {"is_active": False}, format="json").status_code, 404)
        self.assertEqual(self.client.post(reset_url(pk), {"temp_password": TEMP}, format="json").status_code, 404)
        self.assertEqual([r["email"] for r in self.client.get(STAFF_URL).data["results"]], ["b@example.com"])
        with tenant_context(self.business_a):
            role_a = Role.objects.get(name=Role.CASHIER)
        own = self.client.get(STAFF_URL).data["results"][0]["id"]
        self.assertIn("role", self.client.patch(detail_url(own), {"role": str(role_a.pk)}, format="json").data)

    def test_no_delete(self):
        pk = self.add().data["id"]
        self.assertEqual(self.client.delete(detail_url(pk)).status_code, 405)
        self.assertEqual(self.client.put(detail_url(pk), {}, format="json").status_code, 405)
