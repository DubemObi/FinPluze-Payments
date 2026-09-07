from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_root_serves_html():
    response = client.get("/")
    assert response.status_code == 200
    assert "FinPulse Payments" in response.text

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_fund_and_transfer_cycle():
    # 1. Fund
    fund_res = client.post("/api/v1/wallet/fund", json={"email": "demo@finpulse.io", "amount": 20000.0})
    assert fund_res.status_code == 200
    assert fund_res.json()["transaction"]["amount"] == 20000.0

    # 2. Transfer
    transfer_res = client.post("/api/v1/wallet/transfer", json={
        "sender_email": "demo@finpulse.io",
        "recipient_account": "0987654321",
        "recipient_bank": "Kuda Bank",
        "amount": 5000.0,
        "narration": "Automated Test Run"
    })
    assert transfer_res.status_code == 200