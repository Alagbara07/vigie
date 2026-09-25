from fastapi.testclient import TestClient


def test_business_customer_conversation_and_message_round_trip(api_client: TestClient) -> None:
    business = api_client.post(
        "/api/businesses",
        json={"name": "Adaeze Wears", "slug": "adaeze-wears-api"},
    )
    assert business.status_code == 201
    business_id = business.json()["id"]
    assert business.json()["default_currency"] == "NGN"

    customer = api_client.post(
        f"/api/businesses/{business_id}/customers",
        json={"name": "Chinedu Okafor", "contact_identifier": "2348010000001"},
    )
    assert customer.status_code == 201
    assert customer.json()["business_id"] == business_id

    conversation = api_client.post(
        f"/api/businesses/{business_id}/conversations",
        json={"customer_id": customer.json()["id"], "channel": "simulated"},
    )
    assert conversation.status_code == 201
    conversation_id = conversation.json()["id"]

    content = "I sent the ₦150,000 balance yesterday. Please confirm."
    message = api_client.post(
        f"/api/businesses/{business_id}/conversations/{conversation_id}/messages",
        json={
            "sender_type": "customer",
            "sender_identifier": "2348010000001",
            "direction": "inbound",
            "content": content,
            "occurred_at": "2026-09-23T08:15:00Z",
        },
    )
    assert message.status_code == 201
    assert message.json()["content"] == content

    listed = api_client.get(
        f"/api/businesses/{business_id}/conversations/{conversation_id}/messages"
    )
    assert listed.status_code == 200
    assert listed.json()[0]["content"] == content


def test_cross_tenant_customer_is_not_attached(api_client: TestClient) -> None:
    first = api_client.post("/api/businesses", json={"name": "First Shop", "slug": "first-shop"}).json()
    second = api_client.post("/api/businesses", json={"name": "Second Shop", "slug": "second-shop"}).json()
    customer = api_client.post(
        f"/api/businesses/{second['id']}/customers",
        json={"name": "Amaka Bello", "contact_identifier": "2348010000002"},
    ).json()

    response = api_client.post(
        f"/api/businesses/{first['id']}/conversations",
        json={"customer_id": customer["id"], "channel": "simulated"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Customer not found."


def test_duplicate_business_slug_conflicts(api_client: TestClient) -> None:
    payload = {"name": "Adaeze Wears", "slug": "same-slug"}
    assert api_client.post("/api/businesses", json=payload).status_code == 201
    conflict = api_client.post("/api/businesses", json=payload)
    assert conflict.status_code == 409
