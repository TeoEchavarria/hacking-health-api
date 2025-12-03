def test_login_new_user(client):
    """
    Test login with a new user (should trigger registration).
    """
    payload = {
        "username": "testuser",
        "password": "securepassword"
    }
    response = client.post("/login", json=payload)
    
    assert response.status_code == 201
    data = response.json()
    assert "token" in data
    assert "refresh" in data
    assert "expiry" in data
