"""
Tests for the restocking endpoints (recommendations and submitted orders).
"""
import pytest

import mock_data


@pytest.fixture(autouse=True)
def clear_submitted_orders():
    """Submitted orders are module-level state; isolate every test from the others."""
    mock_data.submitted_orders.clear()
    yield
    mock_data.submitted_orders.clear()


def recommend(client, budget):
    response = client.get(f"/api/restocking/recommendations?budget={budget}")
    assert response.status_code == 200
    return response.json()


class TestRestockRecommendations:
    """Test suite for GET /api/restocking/recommendations."""

    def test_zero_budget_recommends_nothing(self, client):
        data = recommend(client, 0)
        assert data["items"] == []
        assert data["total_cost"] == 0
        assert data["remaining_budget"] == 0

    def test_negative_budget_rejected(self, client):
        response = client.get("/api/restocking/recommendations?budget=-1")
        assert response.status_code == 400

    def test_total_never_exceeds_budget(self, client):
        for budget in [5000, 20000, 50000, 120000, 250000, 500000]:
            data = recommend(client, budget)
            assert data["total_cost"] <= budget
            assert data["remaining_budget"] == pytest.approx(budget - data["total_cost"])

    def test_large_budget_ranks_by_gap_descending(self, client):
        items = recommend(client, 500000)["items"]
        assert len(items) > 1
        gaps = [i["gap"] for i in items]
        assert gaps == sorted(gaps, reverse=True)

    def test_items_have_positive_gap_and_consistent_cost(self, client):
        for item in recommend(client, 500000)["items"]:
            assert item["gap"] > 0
            assert item["recommended_qty"] == item["gap"]
            assert item["line_cost"] == pytest.approx(item["recommended_qty"] * item["unit_cost"])
            assert item["lead_time_days"] > 0

    def test_decreasing_demand_item_not_recommended(self, client):
        skus = [i["sku"] for i in recommend(client, 500000)["items"]]
        assert "MTR-304" not in skus

    def test_unaffordable_item_is_skipped_not_end_of_list(self, client):
        # Ranked by gap: FLT-405, GSK-203, WDG-001, SNR-420, CTL-330.
        # At $120K WDG-001 (~$102K) no longer fits after the first two are bought,
        # but the lower-ranked, cheaper SNR-420 (~$26K) still does. A `break`
        # instead of `continue` would stop at WDG-001 and drop SNR-420.
        skus = [i["sku"] for i in recommend(client, 120000)["items"]]
        assert skus == ["FLT-405", "GSK-203", "SNR-420"]

    def test_exact_budget_boundary_is_affordable(self, client):
        # A line costing exactly the remaining budget must be included
        data = recommend(client, 15812.5)
        assert [i["sku"] for i in data["items"]] == ["FLT-405"]
        assert data["remaining_budget"] == 0

    def test_non_finite_budget_rejected(self, client):
        for bad in ("nan", "inf", "-inf"):
            response = client.get(f"/api/restocking/recommendations?budget={bad}")
            assert response.status_code == 400, bad


class TestSubmitRestockOrder:
    """Test suite for POST and GET /api/restocking/orders."""

    def test_place_order_success(self, client):
        items = recommend(client, 500000)["items"]
        payload = {
            "budget": 500000,
            "items": [{"sku": i["sku"], "quantity": i["recommended_qty"]} for i in items],
        }
        response = client.post("/api/restocking/orders", json=payload)
        assert response.status_code == 201

        order = response.json()
        assert order["status"] == "Submitted"
        assert order["order_number"].startswith("RST-")
        assert order["total_value"] == pytest.approx(sum(i["line_cost"] for i in items))
        # An order is delivered when its slowest item is
        assert order["lead_time_days"] == max(i["lead_time_days"] for i in items)

    def test_price_comes_from_server_not_client(self, client):
        payload = {
            "budget": 100000,
            "items": [{"sku": "GSK-203", "quantity": 10, "unit_cost": 0.01}],
        }
        response = client.post("/api/restocking/orders", json=payload)
        assert response.status_code == 201
        assert response.json()["total_value"] == pytest.approx(10 * 42.5)

    def test_rejects_empty_order(self, client):
        response = client.post("/api/restocking/orders", json={"budget": 1000, "items": []})
        assert response.status_code == 400

    def test_rejects_unknown_sku(self, client):
        payload = {"budget": 1000, "items": [{"sku": "NOPE-999", "quantity": 1}]}
        assert client.post("/api/restocking/orders", json=payload).status_code == 400

    @pytest.mark.parametrize("quantity", [0, -5])
    def test_rejects_non_positive_quantity(self, client, quantity):
        payload = {"budget": 100000, "items": [{"sku": "GSK-203", "quantity": quantity}]}
        assert client.post("/api/restocking/orders", json=payload).status_code == 400

    def test_rejects_order_over_budget(self, client):
        payload = {"budget": 100, "items": [{"sku": "CTL-330", "quantity": 86}]}
        assert client.post("/api/restocking/orders", json=payload).status_code == 400

    def test_rejects_sku_with_no_shortfall(self, client):
        # MTR-304 has decreasing demand and is covered by stock
        payload = {"budget": 1e9, "items": [{"sku": "MTR-304", "quantity": 1}]}
        assert client.post("/api/restocking/orders", json=payload).status_code == 400

    def test_rejects_quantity_above_shortfall(self, client):
        # GSK-203 shortfall is 420
        payload = {"budget": 1e9, "items": [{"sku": "GSK-203", "quantity": 421}]}
        assert client.post("/api/restocking/orders", json=payload).status_code == 400

    def test_accepts_quantity_equal_to_shortfall(self, client):
        payload = {"budget": 1e9, "items": [{"sku": "GSK-203", "quantity": 420}]}
        assert client.post("/api/restocking/orders", json=payload).status_code == 201

    def test_rejects_duplicate_sku_lines(self, client):
        # Splitting a quantity across lines must not bypass the per-SKU cap
        payload = {"budget": 1e9, "items": [{"sku": "GSK-203", "quantity": 300}, {"sku": "GSK-203", "quantity": 300}]}
        assert client.post("/api/restocking/orders", json=payload).status_code == 400

    @pytest.mark.parametrize("budget", [-1, "NaN", "Infinity"])
    def test_rejects_invalid_budget(self, client, budget):
        payload = {"budget": budget, "items": [{"sku": "GSK-203", "quantity": 1}]}
        assert client.post("/api/restocking/orders", json=payload).status_code == 422
        assert client.get("/api/restocking/orders").json() == []

    def test_order_total_equal_to_budget_is_accepted(self, client):
        payload = {"budget": 42.5, "items": [{"sku": "GSK-203", "quantity": 1}]}
        assert client.post("/api/restocking/orders", json=payload).status_code == 201

    def test_rejected_order_is_not_stored(self, client):
        client.post("/api/restocking/orders", json={"budget": 1, "items": [{"sku": "CTL-330", "quantity": 1}]})
        assert client.get("/api/restocking/orders").json() == []

    def test_get_orders_newest_first(self, client):
        for qty in (1, 2):
            client.post("/api/restocking/orders", json={"budget": 100000, "items": [{"sku": "GSK-203", "quantity": qty}]})
        orders = client.get("/api/restocking/orders").json()
        assert [o["items"][0]["quantity"] for o in orders] == [2, 1]
        assert orders[0]["order_number"] != orders[1]["order_number"]

    def test_get_orders_empty_by_default(self, client):
        assert client.get("/api/restocking/orders").json() == []

    def test_submitted_orders_not_mixed_into_regular_orders(self, client):
        before = len(client.get("/api/orders").json())
        client.post("/api/restocking/orders", json={"budget": 100000, "items": [{"sku": "GSK-203", "quantity": 1}]})
        assert len(client.get("/api/orders").json()) == before
