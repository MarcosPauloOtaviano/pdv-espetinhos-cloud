import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from app import services
from app.database import init_db
from app.server import create_app


class CommandAccessServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_data_dir = os.environ.get("DUDAIR_DATA_DIR")
        os.environ["DUDAIR_DATA_DIR"] = self.temp_dir.name
        init_db()
        self.command_id = services.create_command("Cliente Teste", "Mesa 7", "admin")

    def tearDown(self):
        if self.previous_data_dir is None:
            os.environ.pop("DUDAIR_DATA_DIR", None)
        else:
            os.environ["DUDAIR_DATA_DIR"] = self.previous_data_dir
        self.temp_dir.cleanup()

    def test_regenerating_access_invalidates_previous_token_without_changing_command(self):
        first = services.generate_command_access(self.command_id, actor="admin")
        same_access = services.get_command_access(self.command_id)

        self.assertEqual(first["token"], same_access["token"])
        self.assertEqual("ativo", same_access["status"])

        second = services.generate_command_access(self.command_id, actor="garcom")

        self.assertNotEqual(first["token"], second["token"])
        self.assertIsNone(services.get_command_by_access_token(first["token"]))
        customer_command = services.get_command_by_access_token(second["token"])
        self.assertEqual(self.command_id, customer_command["id"])
        self.assertEqual("Cliente Teste", customer_command["customer_name"])
        self.assertEqual("Mesa 7", customer_command["table_ref"])

    def test_revoking_access_preserves_command_and_its_totals(self):
        product = services.list_products()[0]
        services.add_item(self.command_id, product["id"], 2, actor="admin")
        before = services.get_command(self.command_id)
        access = services.generate_command_access(self.command_id, actor="admin")

        revoked = services.revoke_command_access(self.command_id, actor="admin")
        after = services.get_command(self.command_id)

        self.assertEqual("revogado", revoked["status"])
        self.assertIsNone(services.get_command_by_access_token(access["token"]))
        self.assertEqual(before["items"], after["items"])
        self.assertEqual(before["total"], after["total"])
        self.assertEqual("aberto", after["status"])

    def test_customer_view_exposes_only_customer_facing_item_fields(self):
        product = services.list_products()[0]
        services.add_item(self.command_id, product["id"], 1, notes="Sem cebola", actor="admin")
        access = services.generate_command_access(self.command_id, actor="admin")

        customer_command = services.get_command_by_access_token(access["token"])

        self.assertEqual(
            {"product_name", "unit_price", "quantity", "subtotal", "notes", "kitchen_status"},
            set(customer_command["items"][0]),
        )

    def test_canceling_command_revokes_active_customer_access(self):
        access = services.generate_command_access(self.command_id, actor="admin")

        services.cancel_command(self.command_id, actor="admin")

        self.assertEqual("revogado", services.get_command_access(self.command_id)["status"])
        self.assertIsNone(services.get_command_by_access_token(access["token"]))

    def test_paying_command_revokes_active_customer_access(self):
        product = services.list_products()[0]
        services.add_item(self.command_id, product["id"], 1, actor="admin")
        command = services.get_command(self.command_id)
        access = services.generate_command_access(self.command_id, actor="admin")
        services.open_cash_session(0, operator_name="Admin", actor="admin")

        services.finalize_command(
            self.command_id,
            [{"method": "dinheiro", "amount": command["total"], "received_amount": command["total"]}],
            actor="admin",
        )

        self.assertEqual("revogado", services.get_command_access(self.command_id)["status"])
        self.assertIsNone(services.get_command_by_access_token(access["token"]))


class CommandAccessApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_data_dir = os.environ.get("DUDAIR_DATA_DIR")
        os.environ["DUDAIR_DATA_DIR"] = self.temp_dir.name
        init_db()
        self.command_id = services.create_command("Cliente API", "Mesa 3", "admin")
        self.client = TestClient(create_app())

    def tearDown(self):
        self.client.close()
        if self.previous_data_dir is None:
            os.environ.pop("DUDAIR_DATA_DIR", None)
        else:
            os.environ["DUDAIR_DATA_DIR"] = self.previous_data_dir
        self.temp_dir.cleanup()

    def _headers(self, username, password):
        response = self.client.post("/api/auth/login", json={"username": username, "password": password})
        self.assertEqual(200, response.status_code)
        return {"Authorization": f"Bearer {response.json()['token']}"}

    def test_only_admin_and_garcom_can_manage_customer_access(self):
        admin = self._headers("admin", "admin123")
        caixa = self._headers("caixa", "caixa123")
        garcom = self._headers("garcom", "garcom123")

        created = self.client.post(f"/api/commands/{self.command_id}/access/regenerate", headers=admin)
        self.assertEqual(200, created.status_code)
        self.assertEqual(403, self.client.get(f"/api/commands/{self.command_id}/access", headers=caixa).status_code)
        self.assertEqual(200, self.client.get(f"/api/commands/{self.command_id}/access", headers=garcom).status_code)

        public = self.client.get("/api/customer/command", params={"token": created.json()["token"]})
        self.assertEqual(200, public.status_code)
        self.assertEqual(self.command_id, public.json()["id"])

    def test_old_public_link_stops_working_after_regeneration(self):
        admin = self._headers("admin", "admin123")
        first = self.client.post(f"/api/commands/{self.command_id}/access/regenerate", headers=admin).json()
        second = self.client.post(f"/api/commands/{self.command_id}/access/regenerate", headers=admin).json()

        self.assertEqual(404, self.client.get("/api/customer/command", params={"token": first["token"]}).status_code)
        self.assertEqual(200, self.client.get("/api/customer/command", params={"token": second["token"]}).status_code)


if __name__ == "__main__":
    unittest.main()
