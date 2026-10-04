"""The WAF route allowlist (infra/app/waf.tf, decision 49) matches the API exactly.

The WAF refuses any API request whose method and path are not in two regex lists. A route added
to the app but not to the lists would answer 404 in production, so every route the app serves
must pass; and the lists must not let through methods, paths or tricks the app does not use.
"""

import re
import uuid
from pathlib import Path

import pytest

from app.main import app

WAF_TF = Path(__file__).resolve().parents[2] / "infra" / "app" / "waf.tf"

# FastAPI's own pages: served by the app, never called by the frontend, refused at the edge.
NOT_EXPOSED = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


def _hcl_list(source: str, name: str) -> list[str]:
    block = re.search(rf"{name}\s*=\s*\[(.*?)\]\n", source, re.S)
    assert block, f"{name} not found in waf.tf"
    return re.findall(r'"([^"]+)"', block.group(1))


def _waf_routes() -> dict[str, list[re.Pattern[str]]]:
    source = WAF_TF.read_text()
    waf_id = re.search(r'waf_id\s*=\s*"([^"]+)"', source).group(1)
    routes = {}
    for method, name in (("GET", "waf_get_routes"), ("POST", "waf_post_routes")):
        patterns = [p.replace("${local.waf_id}", waf_id) for p in _hcl_list(source, name)]
        assert all(len(p) <= 200 for p in patterns)  # WAF limit per regex
        assert len(patterns) <= 10  # WAF limit per regex pattern set
        routes[method] = [re.compile(p) for p in patterns]
    return routes


ROUTES = _waf_routes()


def allowed(method: str, path: str) -> bool:
    return any(p.search(path) for p in ROUTES.get(method, []))


def _sample(path: str) -> str:
    """A real-looking path for a route template: UUIDs, case and customer ids."""
    samples = {
        "session_id": str(uuid.uuid4()),
        "message_id": str(uuid.uuid4()),
        "case_id": "NB-01A0BC",
        "customer_id": "CLI_0001-x",
    }
    return re.sub(r"\{(\w+)\}", lambda m: samples[m.group(1)], path)


def _app_routes() -> list[tuple[str, str]]:
    """Every (method, path template) the API serves, from its OpenAPI schema (it lists the routes
    of the included routers too, which app.routes nests since FastAPI 0.14x)."""
    return [
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    ]


APP_ROUTES = _app_routes()


def test_the_app_routes_are_all_seen():
    # Guards the helper: if it ever finds only a few routes, the checks below prove nothing.
    assert len(APP_ROUTES) >= 15
    assert ("POST", "/v1/chat/sessions/{session_id}/messages") in APP_ROUTES


@pytest.mark.parametrize(("method", "path"), APP_ROUTES)
def test_every_api_route_passes_the_waf(method, path):
    assert allowed(method, _sample(path)), f"{method} {path} is missing from waf.tf"


@pytest.mark.parametrize(
    ("method", "pattern"), [(m, p) for m, patterns in ROUTES.items() for p in patterns]
)
def test_the_allowlist_has_no_route_the_app_lacks(method, pattern):
    assert any(m == method and pattern.search(_sample(p)) for m, p in APP_ROUTES), (
        f"{method} {pattern.pattern} matches no route of the app"
    )


@pytest.mark.parametrize("path", sorted(NOT_EXPOSED))
def test_framework_pages_are_refused(path):
    assert not allowed("GET", path)


SID = str(uuid.uuid4())


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", f"/v1/chat/sessions/{SID}/messages"),  # POST-only routes
        ("GET", "/v1/auth/login"),
        ("POST", "/health"),  # GET-only routes
        ("POST", "/v1/metrics/live"),
        ("OPTIONS", "/v1/chat/sessions"),
        ("PUT", "/v1/auth/login"),
        ("DELETE", "/v1/agent/cases/NB-01A0BC"),
        ("HEAD", "/health"),
        ("GET", "/v1/nonexistent"),
        ("GET", "/v1/metrics/live/"),  # trailing slash
        ("POST", "/v1/auth/login/"),
        ("GET", "/health/x"),
        ("POST", "/v1//chat/sessions"),
        ("GET", "/v1/demo/customers/../../etc/passwd"),  # traversal
        ("GET", "/v1/demo/customers/%2e%2e"),  # encoded
        ("GET", "/v1/demo/customers/a%00"),
        ("GET", "/v1/demo/customers/" + "a" * 65),  # longer than any id
        ("POST", "/v1/agent/cases/NB-01A0BC/delete"),  # unknown action
        ("POST", f"/v1/public/chat/sessions/{SID}/handoff"),  # no handoff for the public chat
    ],
)
def test_unknown_methods_and_paths_are_refused(method, path):
    assert not allowed(method, path)
