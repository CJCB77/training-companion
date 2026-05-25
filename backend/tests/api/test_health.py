def test_health_check(client):
    endpoint = "/health"

    response = client.get(endpoint)
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["service"] == "training-companion-api"