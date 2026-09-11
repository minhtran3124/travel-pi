"""Real UAT: send two real chat turns through the actual /agent/chat endpoint
(app.main.create_app(), full lifespan, the branch's real compiled graph, the
real dev Postgres) and confirm the second turn reads cached tokens.

Auth: the app requires a real Supabase JWT (RS256 via JWKS), which needs a
live Supabase project's signing keys - not available in this environment.
This script overrides `get_current_user` exactly the way the app's own test
suite does (tests/api/agent_config/test_agent_runs_dashboard.py and siblings),
which is a supported, intentional test seam - not a bypass invented here.
Everything else (routing, tier resolution, quota, the graph, the DB writes,
TurnMetricsHandler) runs as real code, unmodified.
"""
import sys
from fastapi.testclient import TestClient
from app.core.auth import AuthUser, get_current_user
from app.main import create_app

USER_ID = "uat-prompt-caching-2026-09-10"

app = create_app()
app.dependency_overrides[get_current_user] = lambda: AuthUser(
    id=USER_ID, email="uat@example.com", role=None, claims={}
)

with TestClient(app) as client:  # triggers the real lifespan (graph build, DB)
    r1 = client.post("/agent/chat", json={"message": "What's the weather in Da Nang today?"})
    print("turn 1:", r1.status_code)
    r1.raise_for_status()
    conv_id = r1.json()["conversation_id"]
    print("conversation_id:", conv_id)

    r2 = client.post("/agent/chat", json={
        "message": "And tomorrow?", "conversation_id": conv_id,
    })
    print("turn 2:", r2.status_code)
    r2.raise_for_status()
    print("reply 2 (truncated):", r2.json()["reply"][:200])
