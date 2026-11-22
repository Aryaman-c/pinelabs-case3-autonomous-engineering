from starlette.requests import Request
import api.server
from api.server import app, templates, WorkflowStartRequest, DecisionRequest


def test_server_import():
    assert api.server.app is not None


def test_dashboard_render():
    req = Request(scope={"type": "http"})
    res = templates.TemplateResponse(request=req, name="dashboard.html")
    assert res is not None


def test_pydantic_models():
    start_req = WorkflowStartRequest(requirement="Test requirement")
    assert start_req.requirement == "Test requirement"

    decision_req = DecisionRequest(action="approve", critique="Looks great")
    assert decision_req.action == "approve"
    assert decision_req.critique == "Looks great"
