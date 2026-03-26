def test_public_feed_is_accessible(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Quiet Atlas" in response.data
    assert b"Spaces" in response.data


def test_login_success_redirects_to_feed(client):
    response = client.post(
        "/login",
        data={"username": "admin", "password": "password123"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_login_failure_shows_error(client):
    response = client.post(
        "/login",
        data={"username": "admin", "password": "wrong-password"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Invalid username or password." in response.data
