"""
Tests for the purchase order endpoints and their link to backlog items.
"""
from datetime import date, timedelta

import pytest

import mock_data


@pytest.fixture(autouse=True)
def clear_purchase_orders():
    """Purchase orders are module-level state; isolate every test from the others."""
    mock_data.purchase_orders.clear()
    yield
    mock_data.purchase_orders.clear()


def future(days=14):
    return (date.today() + timedelta(days=days)).isoformat()


def po_payload(backlog_item_id="1", **overrides):
    payload = {
        "backlog_item_id": backlog_item_id,
        "supplier_name": "Acme Supply Co",
        "quantity": 350,
        "unit_cost": 12.5,
        "expected_delivery_date": future(),
        "notes": "Rush order",
    }
    payload.update(overrides)
    return payload


class TestPurchaseOrderEndpoints:
    """Test suite for /api/purchase-orders endpoints."""

    def test_create_purchase_order(self, client):
        """Test creating a PO returns 201 with server-assigned fields."""
        response = client.post("/api/purchase-orders", json=po_payload())
        assert response.status_code == 201

        po = response.json()
        assert po["id"].startswith("PO-")
        assert po["backlog_item_id"] == "1"
        assert po["supplier_name"] == "Acme Supply Co"
        assert po["quantity"] == 350
        assert po["unit_cost"] == 12.5
        assert po["expected_delivery_date"] == future()
        assert po["status"] == "Ordered"
        assert po["created_date"] == date.today().isoformat()
        assert po["notes"] == "Rush order"

    def test_create_purchase_order_without_notes(self, client):
        """Test that notes are optional."""
        payload = po_payload()
        del payload["notes"]
        response = client.post("/api/purchase-orders", json=payload)
        assert response.status_code == 201
        assert response.json()["notes"] is None

    def test_create_purchase_order_trims_supplier(self, client):
        """Test that surrounding whitespace is stripped from the supplier name."""
        response = client.post("/api/purchase-orders", json=po_payload(supplier_name="  Acme  "))
        assert response.status_code == 201
        assert response.json()["supplier_name"] == "Acme"

    def test_create_purchase_order_today_is_allowed(self, client):
        """Test that a delivery date of today is not treated as the past."""
        response = client.post(
            "/api/purchase-orders",
            json=po_payload(expected_delivery_date=date.today().isoformat()),
        )
        assert response.status_code == 201

    def test_create_purchase_order_unknown_backlog_item(self, client):
        """Test that a PO for a nonexistent backlog item is a 404."""
        response = client.post("/api/purchase-orders", json=po_payload(backlog_item_id="nonexistent-999"))
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
        assert mock_data.purchase_orders == []

    def test_create_purchase_order_past_delivery_date_rejected(self, client):
        """Test that a delivery date in the past is rejected."""
        past = (date.today() - timedelta(days=1)).isoformat()
        response = client.post("/api/purchase-orders", json=po_payload(expected_delivery_date=past))
        assert response.status_code == 400
        assert "past" in response.json()["detail"].lower()
        assert mock_data.purchase_orders == []

    def test_duplicate_purchase_order_rejected(self, client):
        """Test that a backlog item can only have one PO."""
        assert client.post("/api/purchase-orders", json=po_payload()).status_code == 201

        response = client.post("/api/purchase-orders", json=po_payload(supplier_name="Other Supplier"))
        assert response.status_code == 409
        assert len(mock_data.purchase_orders) == 1
        assert mock_data.purchase_orders[0]["supplier_name"] == "Acme Supply Co"

    @pytest.mark.parametrize("overrides", [
        {"supplier_name": ""},
        {"supplier_name": "   "},
        {"supplier_name": "x" * 101},
        {"quantity": 0},
        {"quantity": -5},
        {"quantity": 1_000_001},
        {"quantity": 1.5},
        {"unit_cost": -0.01},
        {"unit_cost": "abc"},
        {"expected_delivery_date": "not-a-date"},
        {"expected_delivery_date": "2025-13-45"},
        {"notes": "x" * 501},
    ])
    def test_create_purchase_order_invalid_input_rejected(self, client, overrides):
        """Test that out-of-range or malformed fields are rejected with 422."""
        response = client.post("/api/purchase-orders", json=po_payload(**overrides))
        assert response.status_code == 422
        assert mock_data.purchase_orders == []

    @pytest.mark.parametrize("bad_cost", ["NaN", "Infinity"])
    def test_create_purchase_order_non_finite_unit_cost_rejected(self, client, bad_cost):
        """Test that NaN/Infinity unit costs cannot be smuggled in as raw JSON."""
        body = (
            '{"backlog_item_id": "1", "supplier_name": "Acme", "quantity": 1, '
            f'"unit_cost": {bad_cost}, "expected_delivery_date": "{future()}"}}'
        )
        response = client.post(
            "/api/purchase-orders", content=body, headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422
        assert mock_data.purchase_orders == []

    def test_create_purchase_order_missing_fields_rejected(self, client):
        """Test that required fields must be present."""
        response = client.post("/api/purchase-orders", json={"backlog_item_id": "1"})
        assert response.status_code == 422

    def test_purchase_order_ids_unique(self, client):
        """Test that POs for different backlog items get distinct ids."""
        backlog = client.get("/api/backlog").json()
        assert len(backlog) >= 2

        ids = [
            client.post("/api/purchase-orders", json=po_payload(backlog_item_id=item["id"])).json()["id"]
            for item in backlog[:2]
        ]
        assert len(set(ids)) == 2

    def test_get_purchase_order_by_backlog_item(self, client):
        """Test fetching a PO by its backlog item id."""
        created = client.post("/api/purchase-orders", json=po_payload()).json()

        response = client.get("/api/purchase-orders/1")
        assert response.status_code == 200
        assert response.json() == created

    def test_get_purchase_order_path_is_backlog_item_id_not_po_id(self, client):
        """Test that looking up by the PO's own id does not resolve."""
        created = client.post("/api/purchase-orders", json=po_payload()).json()
        response = client.get(f"/api/purchase-orders/{created['id']}")
        assert response.status_code == 404

    def test_get_purchase_order_none_exists(self, client):
        """Test fetching a PO for a backlog item that has none."""
        response = client.get("/api/purchase-orders/1")
        assert response.status_code == 404
        assert "no purchase order" in response.json()["detail"].lower()


class TestBacklogPurchaseOrderLink:
    """Test that /api/backlog reflects purchase orders (drives Create PO vs View PO)."""

    def test_backlog_has_no_po_by_default(self, client):
        """Test that with no POs every backlog item is flagged as having none."""
        for item in client.get("/api/backlog").json():
            assert item["has_purchase_order"] is False
            assert item["purchase_order_id"] is None

    def test_backlog_reflects_created_po(self, client):
        """Test that only the item with a PO carries its id after creation."""
        created = client.post("/api/purchase-orders", json=po_payload(backlog_item_id="2")).json()

        for item in client.get("/api/backlog").json():
            if item["id"] == "2":
                assert item["has_purchase_order"] is True
                assert item["purchase_order_id"] == created["id"]
            else:
                assert item["has_purchase_order"] is False
                assert item["purchase_order_id"] is None
