"""render.yaml static checks: parses, and is wired to what the code actually provides."""

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[4]
BLUEPRINT = ROOT / "render.yaml"
SCRIPT_ENV = {
    "WEB_CONCURRENCY",
    "GUNICORN_TIMEOUT",
    "GUNICORN_GRACEFUL_TIMEOUT",
    "GUNICORN_KEEPALIVE",
}


@pytest.fixture(scope="module")
def bp() -> dict:
    return yaml.safe_load(BLUEPRINT.read_text())


def _service(bp: dict, name: str) -> dict:
    return next(s for s in bp["services"] if s["name"] == name)


def _group(bp: dict) -> dict:
    return {g["name"]: g for g in bp["envVarGroups"]}["travel-pi-api"]


def test_web_health_check_and_instances(bp):
    web = _service(bp, "travel-pi-api")
    assert web["healthCheckPath"] == "/readyz"
    assert web["numInstances"] == 2
    assert web["preDeployCommand"] == "alembic upgrade head"


def test_files_referenced_exist(bp):
    web = _service(bp, "travel-pi-api")
    assert (ROOT / web["dockerfilePath"]).is_file()
    assert (ROOT / "apps/api/docker/start-web.sh").is_file()
    assert (
        _service(bp, "travel-pi-worker")["dockerCommand"]
        == "arq app.worker.WorkerSettings"
    )


def test_env_names_are_real_settings(bp):
    from app.core.config import Settings

    fields = {f.upper() for f in Settings.model_fields}
    keys = [v["key"] for v in _group(bp)["envVars"]]
    for svc in ("travel-pi-api", "travel-pi-worker"):
        keys += [v["key"] for v in _service(bp, svc)["envVars"] if "key" in v]
    for key in keys:
        assert key in fields or key in SCRIPT_ENV, key


def test_no_secret_values_committed(bp):
    for var in _group(bp)["envVars"]:
        if var["key"].endswith("_KEY"):
            assert (
                var.get("sync") is False or var.get("generateValue") is True
            ) and "value" not in var
    for svc in bp["services"]:
        for var in svc.get("envVars", []):
            if var.get("key") == "DATABASE_URL":
                assert var.get("sync") is False and "value" not in var


def test_supabase_auth_is_configured_and_documented(bp):
    """Without a Supabase URL/ref the API cannot verify tokens: every authed route 401s."""
    entry = next((v for v in _group(bp)["envVars"] if v["key"] == "SUPABASE_URL"), None)
    assert entry is not None and entry.get("sync") is False
    assert "SUPABASE_URL" in (ROOT / "docs/render-deploy.md").read_text()


def test_dashboard_credentials_are_declared_and_documented(bp):
    """The dashboard fails closed without these; the operator must be prompted for them."""
    env = {v["key"]: v for v in _group(bp)["envVars"]}
    for key in ("DASHBOARD_BASIC_USER", "DASHBOARD_BASIC_PASSWORD"):
        assert env[key].get("sync") is False and "value" not in env[key]
    secret = env["DASHBOARD_SECRET_KEY"]
    assert secret.get("generateValue") is True and "value" not in secret
    runbook = (ROOT / "docs/render-deploy.md").read_text()
    assert "DASHBOARD_BASIC_PASSWORD" in runbook


def test_pool_budget_fits_documented_max_connections(bp):
    env = {v["key"]: v.get("value") for v in _group(bp)["envVars"]}
    base = int(env["DB_POOL_SIZE"]) + int(env["DB_MAX_OVERFLOW"]) + 2
    web_per_proc = base + int(env["DB_LOCK_POOL_SIZE"])  # lock pool is web-only
    web = _service(bp, "travel-pi-api")
    workers = int(
        next(v["value"] for v in web["envVars"] if v.get("key") == "WEB_CONCURRENCY")
    )
    total = web["numInstances"] * workers * web_per_proc + base  # + the Arq worker
    runbook = (ROOT / "docs/render-deploy.md").read_text()
    assert "max_connections` must be at least 100" in runbook
    assert total <= 0.8 * 100  # runbook: needs max_connections >= 100
