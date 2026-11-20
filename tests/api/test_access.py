"""ACCESS-01 and ACCESS-02: real authentication and account boundaries."""


def test_access_01_registration_session_and_logout(clients):
    client = clients()
    credentials = {"email": "new@example.com", "password": "abcdefgh"}
    assert client.post("/auth/register", json=credentials).status_code == 201
    assert client.post("/auth/login", json=credentials).status_code == 200
    assert client.get("/bookings").status_code == 200
    assert client.post("/auth/logout").status_code == 204
    assert client.get("/bookings").status_code == 401


def test_access_02_other_account_cannot_view_edit_or_cancel(
    owner, other, payload, windows, reserve
):
    booking_id = reserve(owner, payload)
    original = owner.get("/bookings").json()
    assert other.get("/bookings").json() == []
    assert (
        other.patch(
            f"/bookings/{booking_id}", json={"slots": windows([16])}
        ).status_code
        == 404
    )
    assert other.post(f"/bookings/{booking_id}/cancel").status_code == 404
    assert owner.get("/bookings").json() == original
