from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def test_index_page_is_served():
    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    assert "DBAgent" in response.text
    assert "/static/app.js" in response.text


def test_frontend_assets_exist():
    static_dir = Path("app/static")

    assert (static_dir / "index.html").exists()
    assert (static_dir / "styles.css").exists()
    assert (static_dir / "app.js").exists()
