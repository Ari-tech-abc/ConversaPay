"""HTTP contracts with providers mocked; no real email or database writes."""
import unittest
from unittest.mock import MagicMock, patch
from test_application_security import app, AuthUser, get_current_user, require_auth, TestClient
from backend.routers import products, profile, api_keys

BID = "00000000-0000-4000-8000-000000000001"
PID = "00000000-0000-4000-8000-000000000002"


class BulkSettingsApiTests(unittest.TestCase):
    def setUp(self):
        self.user = AuthUser("owner-id", "owner@example.com", True)
        app.dependency_overrides[get_current_user] = lambda: self.user
        app.dependency_overrides[require_auth] = lambda: self.user
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.client.close()

    def test_selected_deletion_passes_authenticated_owner_to_atomic_rpc(self):
        db = MagicMock(); db.rpc.return_value.execute.return_value.data = 1
        with patch.object(products, "supabase", db), patch.object(products, "require_business_owner_for_business_id", return_value=BID):
            response = self.client.post('/api/v1/products/bulk-delete', json={"business_id": BID, "product_ids": [PID], "expected_count": 1})
        self.assertEqual(response.json(), {"deleted": 1})
        self.assertEqual(db.rpc.call_args.args[1]["p_user_id"], "owner-id")

    def test_invalid_or_ambiguous_selection_never_reaches_database(self):
        with patch.object(products, "supabase") as db:
            for payload in [{"product_ids": []}, {"product_ids": [PID, PID]}, {"product_ids": [PID], "all_products": True}, {"product_ids": [PID], "expected_count": 2}]:
                response = self.client.post('/api/v1/products/bulk-delete', json={"business_id": BID, "expected_count": 1, **payload})
                self.assertEqual(response.status_code, 422)
        db.rpc.assert_not_called()

    def test_large_catalog_starts_a_job_instead_of_one_long_delete(self):
        db=MagicMock();db.rpc.return_value.execute.return_value.data={"job_id":PID,"status":"pending","total":15000}
        with patch.object(products,"supabase",db),patch.object(products,"require_business_owner_for_business_id",return_value=BID):
            response=self.client.post('/api/v1/products/bulk-delete',json={"business_id":BID,"all_products":True,"expected_count":15000})
        self.assertEqual(response.json()["job_id"],PID)
        self.assertEqual(db.rpc.call_args.args[0],"start_product_delete_job")

    def test_job_progress_is_scoped_to_authenticated_owner(self):
        db=MagicMock();db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data=[]
        with patch.object(products,"supabase",db):
            response=self.client.get('/api/v1/products/delete-jobs/'+PID)
        self.assertEqual(response.status_code,404)
        db.table.return_value.select.return_value.eq.return_value.eq.assert_called_once_with('user_id','owner-id')

    def test_changed_selection_returns_conflict_without_partial_delete(self):
        class Conflict(Exception):
            code = "P0001"
        db = MagicMock(); db.rpc.return_value.execute.side_effect = Conflict("Selection changed")
        with patch.object(products, "supabase", db), patch.object(products, "require_business_owner_for_business_id", return_value=BID):
            response = self.client.post('/api/v1/products/bulk-delete', json={"business_id": BID, "all_products": True, "expected_count": 55})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "selection_changed")

    def test_storage_failure_never_reports_a_fake_free_plan(self):
        db = MagicMock(); db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.side_effect = RuntimeError("offline")
        with patch.object(profile, "supabase", db):
            response = self.client.get('/api/v1/profile/billing')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["code"], "settings_unavailable")
        self.assertNotIn("plan_type", response.json())

    def test_empty_preferences_do_not_opt_into_product_updates(self):
        db = MagicMock(); db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{"notification_preferences": {}}]
        with patch.object(profile, "supabase", db):
            response = self.client.get('/api/v1/profile/notifications')
        self.assertFalse(response.json()["preferences"]["product_updates"])

    def test_api_key_storage_failure_is_specific_and_safe(self):
        db = MagicMock(); db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.side_effect = RuntimeError("secret connection failure")
        with patch.object(api_keys, "supabase", db), patch.object(api_keys, "_owned_business", return_value=True), patch.object(api_keys, "get_user_plan", return_value={"plan_type": "pro"}):
            response = self.client.get('/api/v1/api-keys?business_id=' + BID)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["code"], "api_keys_unavailable")
        self.assertNotIn("secret", response.text)


if __name__ == '__main__':
    unittest.main()
