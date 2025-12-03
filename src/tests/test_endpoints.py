def test_read_main(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Hacking Health API is running"}

def test_health_sensor_data(client):
    payload = {
        "records": [
            {
                "deviceId": "device_123",
                "timestamp": 1701550000,
                "x": 0.1,
                "y": 0.2,
                "z": 0.3,
                "source": "test_watch"
            }
        ]
    }
    response = client.post("/health/sensor-data", json=payload)
    assert response.status_code == 200
    assert response.json() == {"status": "success", "count": 1}

def test_txagent_query(client):
    payload = {
        "query": "I have a headache",
        "medical_history": "None",
        "pdf_summaries": []
    }
    response = client.post("/txagent/query", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "reasoning_chain" in data
    assert "structured_output" in data
    assert "citations" in data
