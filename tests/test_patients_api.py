import uuid


def _create(client, payload):
    resp = client.post("/patients", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


class TestCreate:
    def test_create_returns_201_with_envelope(self, client, valid_patient):
        resp = client.post("/patients", json=valid_patient)
        assert resp.status_code == 201
        body = resp.json()
        assert body["error"] is None
        data = body["data"]
        assert uuid.UUID(data["patient_id"])
        assert data["phone_number"] == "3055550142"  # normalized
        assert data["state"] == "FL"  # full name normalized to abbreviation
        assert data["date_of_birth"] == "04/12/1985"  # spec output format
        assert data["preferred_language"] == "English"  # default

    def test_create_invalid_returns_422_envelope(self, client, valid_patient):
        valid_patient["phone_number"] = "123"
        valid_patient["date_of_birth"] = "12/31/2999"
        resp = client.post("/patients", json=valid_patient)
        assert resp.status_code == 422
        body = resp.json()
        assert body["data"] is None
        assert body["error"]["code"] == "validation_error"
        fields = {d["field"] for d in body["error"]["details"]}
        assert {"phone_number", "date_of_birth"} <= fields

    def test_missing_required_field_422(self, client, valid_patient):
        del valid_patient["last_name"]
        assert client.post("/patients", json=valid_patient).status_code == 422


class TestReadAndFilters:
    def test_get_by_id(self, client, valid_patient):
        created = _create(client, valid_patient)
        resp = client.get(f"/patients/{created['patient_id']}")
        assert resp.status_code == 200
        assert resp.json()["data"]["first_name"] == "Maria"

    def test_get_bad_uuid_is_422(self, client):
        assert client.get("/patients/not-a-uuid").status_code == 422

    def test_get_missing_is_404(self, client):
        resp = client.get(f"/patients/{uuid.uuid4()}")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"

    def test_list_and_filters(self, client, valid_patient):
        _create(client, valid_patient)
        other = dict(valid_patient, first_name="Ana", last_name="Lopez", phone_number="3055550199")
        _create(client, other)

        assert len(client.get("/patients").json()["data"]) == 2
        by_name = client.get("/patients", params={"last_name": "garcia"}).json()["data"]
        assert len(by_name) == 1 and by_name[0]["last_name"] == "Garcia"
        by_phone = client.get("/patients", params={"phone_number": "(305) 555-0199"}).json()["data"]
        assert len(by_phone) == 1 and by_phone[0]["first_name"] == "Ana"
        by_dob = client.get("/patients", params={"date_of_birth": "04/12/1985"}).json()["data"]
        assert len(by_dob) == 2


class TestUpdateAndDelete:
    def test_partial_update(self, client, valid_patient):
        created = _create(client, valid_patient)
        resp = client.put(
            f"/patients/{created['patient_id']}",
            json={"city": "Orlando", "insurance_provider": "Aetna"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["city"] == "Orlando"
        assert data["insurance_provider"] == "Aetna"
        assert data["first_name"] == "Maria"  # untouched

    def test_update_invalid_field_422(self, client, valid_patient):
        created = _create(client, valid_patient)
        resp = client.put(f"/patients/{created['patient_id']}", json={"zip_code": "12"})
        assert resp.status_code == 422

    def test_soft_delete(self, client, valid_patient):
        created = _create(client, valid_patient)
        pid = created["patient_id"]

        resp = client.delete(f"/patients/{pid}")
        assert resp.status_code == 200
        assert resp.json()["data"]["deleted_at"] is not None

        # Gone from reads/list, but not hard-deleted (delete again -> 404).
        assert client.get(f"/patients/{pid}").status_code == 404
        assert client.get("/patients").json()["data"] == []
        assert client.delete(f"/patients/{pid}").status_code == 404
