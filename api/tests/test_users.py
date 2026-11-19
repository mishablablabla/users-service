USER = {"name": "Ada Lovelace", "email": "ada@example.com"}


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_list_empty(client):
    r = client.get("/api/users")
    assert r.status_code == 200
    assert r.json() == []


def test_create_returns_201_and_location(client):
    r = client.post("/api/users", json=USER)
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == 1
    assert body["name"] == USER["name"]
    assert r.headers["location"] == "/api/users/1"


def test_get_by_id(client):
    uid = client.post("/api/users", json=USER).json()["id"]
    r = client.get(f"/api/users/{uid}")
    assert r.status_code == 200
    assert r.json()["email"] == USER["email"]


def test_get_missing_returns_404(client):
    assert client.get("/api/users/999").status_code == 404


def test_update(client):
    uid = client.post("/api/users", json=USER).json()["id"]
    r = client.put(f"/api/users/{uid}", json={"name": "Grace", "email": "grace@example.com"})
    assert r.status_code == 200
    assert r.json()["name"] == "Grace"
    assert client.get(f"/api/users/{uid}").json()["email"] == "grace@example.com"


def test_update_missing_returns_404(client):
    assert client.put("/api/users/999", json=USER).status_code == 404


def test_delete(client):
    uid = client.post("/api/users", json=USER).json()["id"]
    assert client.delete(f"/api/users/{uid}").status_code == 204
    assert client.get(f"/api/users/{uid}").status_code == 404


def test_delete_missing_returns_404(client):
    assert client.delete("/api/users/999").status_code == 404


def test_duplicate_email_returns_409(client):
    client.post("/api/users", json=USER)
    r = client.post("/api/users", json={"name": "Other", "email": USER["email"]})
    assert r.status_code == 409


def test_validation_error_returns_422(client):
    assert client.post("/api/users", json={"name": "", "email": "nope"}).status_code == 422


def test_list_returns_created(client):
    client.post("/api/users", json=USER)
    client.post("/api/users", json={"name": "Grace", "email": "grace@example.com"})
    assert [u["name"] for u in client.get("/api/users").json()] == ["Ada Lovelace", "Grace"]


def test_openapi_and_swagger_available(client):
    assert client.get("/api/openapi.json").status_code == 200
    assert client.get("/api/docs").status_code == 200
