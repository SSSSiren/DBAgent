from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def test_index_page_is_served():
    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    assert "DBAgent" in response.text
    assert "/static/app.js" in response.text
    assert 'id="latestSql"' in response.text
    assert 'id="copySqlBtn"' in response.text
    assert 'id="confirmBtn" class="secondary" type="button" disabled hidden' in response.text


def test_frontend_assets_exist():
    static_dir = Path("app/static")

    assert (static_dir / "index.html").exists()
    assert (static_dir / "styles.css").exists()
    assert (static_dir / "app.js").exists()


def test_frontend_latest_sql_logic_exists():
    script = Path("app/static/app.js").read_text()
    styles = Path("app/static/styles.css").read_text()

    assert "function updateLatestSql" in script
    assert "navigator.clipboard.writeText" in script
    assert "finalPayload.latest_sql" in script
    assert "latestSqlFromToolCalls(finalPayload.tool_calls)" in script
    assert "updateLatestSql(data.latest_sql)" in script
    assert "function setConfirmationMode" in script
    assert "sendBtn.hidden = needsConfirmation" in script
    assert "confirmBtn.hidden = !needsConfirmation" in script
    assert ".sql-box" in styles
