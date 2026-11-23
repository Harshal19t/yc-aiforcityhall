"""Tests for the LLM client, agents and pipeline. No real model needed."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from pdcheck.agents.agents import evidence_in_text, run_extractor, run_router
from pdcheck.agents.pipeline import run_pipeline
from pdcheck.agents.schemas import ExtractorOutput, RouterOutput, llm_schema
from pdcheck.llm.client import FakeClient, LLMUnavailable, OllamaClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def responder(router: dict, extractor: dict | None = None):
    """Fake LLM: answers the router prompt with `router`, the extractor prompt with `extractor`."""
    def _respond(system: str, user: str, schema: dict) -> dict:
        if "classify" in system:
            return router
        return extractor or {"extensions": [], "dwelling_type": None, "cladding": False,
                             "cladding_evidence": None, "rear_depth_m": None, "height_m": None}
    return _respond


def ext(**kw) -> dict:
    base = {"extensions": [], "dwelling_type": None, "cladding": False,
            "cladding_evidence": None, "rear_depth_m": None, "height_m": None}
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# Schema + grounding
# ---------------------------------------------------------------------------

def test_llm_schema_is_flat():
    for model in (RouterOutput, ExtractorOutput):
        assert "$ref" not in json.dumps(llm_schema(model))
        assert "$defs" not in llm_schema(model)


def test_evidence_matching_ignores_case_and_punctuation():
    src = "erection of a hip-to-gable and rear dormer roof extension"
    assert evidence_in_text("Hip to gable", src)
    assert evidence_in_text("rear dormer roof extension", src)
    assert not evidence_in_text("two-storey side extension", src)


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

def test_router_flags_hallucinated_evidence():
    client = FakeClient(responder({"householder": True, "items": [
        {"work_type": "roof_enlargement", "evidence": "rear dormer"},
        {"work_type": "solar", "evidence": "solar panels to rear"},  # not in text
    ]}))
    out, step = run_router(client, "erection of 1no. rear dormer")
    assert step.ok
    assert step.hallucinated_evidence == ["solar panels to rear"]


def test_extractor_drops_invented_numbers():
    client = FakeClient(responder({}, ext(
        extensions=[{"position": "rear", "storeys": 1, "evidence": "single-storey rear extension"}],
        rear_depth_m=3.0, height_m=None,
    )))
    out, step = run_extractor(client, "erection of single-storey rear extension")
    assert out.rear_depth_m is None  # 3.0 is not written in the text
    assert "rear_depth_m=3.0" in step.hallucinated_evidence


def test_extractor_keeps_numbers_that_are_in_text():
    client = FakeClient(responder({}, ext(rear_depth_m=3.5)))
    out, _ = run_extractor(client, "single-storey rear extension projecting 3.5m")
    assert out.rear_depth_m == 3.5


def test_invalid_output_is_retried_then_accepted():
    answers = [{"householder": "maybe", "items": "x"},
               {"householder": True, "items": [{"work_type": "outbuilding", "evidence": "a shed"}]}]
    client = FakeClient(lambda s, u, sc: answers.pop(0))
    out, step = run_router(client, "erection of a shed")
    assert step.ok and step.attempts == 2
    assert out.items[0].work_type == "outbuilding"


def test_persistently_invalid_output_fails_softly():
    client = FakeClient(lambda s, u, sc: {"nonsense": 1})
    out, step = run_router(client, "erection of a shed")
    assert out is None and not step.ok and step.error


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def test_non_householder_is_out_of_scope():
    client = FakeClient(responder({"householder": False, "items": [
        {"work_type": "non_householder", "evidence": "fencing to perimeter of school field"}]}))
    res = run_pipeline("erection of 2m high fencing to perimeter of school field", client)
    assert res.status == "out_of_scope"
    assert len(client.calls) == 1  # extractor is skipped


def test_dormer_goes_to_officer_review_with_class_b_citation():
    client = FakeClient(responder({"householder": True, "items": [
        {"work_type": "roof_enlargement", "evidence": "rear dormer"}]}))
    res = run_pipeline("Application for Lawful Development Certificate for the erection of 1no. rear dormer", client)
    assert res.description == "the erection of 1no. rear dormer"  # boilerplate stripped
    assert res.status == "needs_review"
    assert res.items[0].findings[0]["citation"] == "GPDO 2015 Sch 2 Pt 1 Class B"


def test_extension_runs_through_deterministic_engine():
    client = FakeClient(responder(
        {"householder": True, "items": [{"work_type": "extension", "evidence": "single-storey rear extension"}]},
        ext(extensions=[{"position": "rear", "storeys": 1, "evidence": "single-storey rear extension"}]),
    ))
    res = run_pipeline("single-storey rear extension", client,
                       known={"dwelling_type": "semi", "rear_depth_m": 3.8})
    assert res.status == "prior_approval_possible"
    assert any(f["rule_id"] == "rear_depth_other_basic" for f in res.items[0].findings)


def test_user_confirmed_fields_override_extraction():
    client = FakeClient(responder(
        {"householder": True, "items": [{"work_type": "extension", "evidence": "rear extension"}]},
        ext(extensions=[{"position": "rear", "storeys": 1, "evidence": "rear extension"}], dwelling_type="detached"),
    ))
    res = run_pipeline("rear extension", client, known={"dwelling_type": "flat"})
    assert res.status == "needs_permission"  # flats have no Class A rights


def test_side_rear_extension_is_checked_against_both_rule_sets():
    client = FakeClient(responder(
        {"householder": True, "items": [{"work_type": "extension", "evidence": "side/rear extension"}]},
        ext(extensions=[{"position": "side_rear", "storeys": 2, "evidence": "side/rear extension"}]),
    ))
    res = run_pipeline("two-storey side/rear extension", client)
    ids = {f["rule_id"] for f in res.items[0].findings}
    assert "side_extension_single_storey_only" in ids  # side rule fired
    assert res.status == "needs_permission"


def test_constraints_from_lookup_reach_the_engine():
    client = FakeClient(responder(
        {"householder": True, "items": [{"work_type": "external_alteration", "evidence": "render"}]},
        ext(cladding=True, cladding_evidence="render"),
    ))
    res = run_pipeline("render to front elevation", client, known={"article_2_3_land": True})
    assert any(f["rule_id"] == "article_2_3_no_cladding" for f in res.items[0].findings)
    assert res.status == "needs_permission"


# ---------------------------------------------------------------------------
# Ollama client against a local fake server
# ---------------------------------------------------------------------------

class _FakeOllama(BaseHTTPRequestHandler):
    reject_think = False
    requests: list[dict] = []

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).requests.append(body)
        if type(self).reject_think and "think" in body:
            self._send(400, {"error": "model does not support think"})
            return
        if body["model"] == "missing":
            self._send(404, {"error": "model not found"})
            return
        content = json.dumps({"householder": True, "items": []})
        self._send(200, {"message": {"role": "assistant", "content": content}})

    def _send(self, code, payload):
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


@pytest.fixture
def ollama():
    _FakeOllama.reject_think = False
    _FakeOllama.requests = []
    server = HTTPServer(("127.0.0.1", 0), _FakeOllama)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_ollama_request_shape_and_cache(ollama, tmp_path):
    client = OllamaClient(model="qwen3:4b", base_url=ollama, cache_dir=tmp_path)
    schema = llm_schema(RouterOutput)
    first = client.complete_json("sys", "user", schema)
    second = client.complete_json("sys", "user", schema)
    assert first.data == {"householder": True, "items": []}
    assert not first.cached and second.cached
    assert len(_FakeOllama.requests) == 1  # second answer came from disk
    req = _FakeOllama.requests[0]
    assert req["format"] == schema and req["stream"] is False
    assert req["options"]["temperature"] == 0 and req["think"] is False


def test_ollama_retries_without_think_if_model_rejects_it(ollama, tmp_path):
    _FakeOllama.reject_think = True
    client = OllamaClient(model="llama3.2:3b", base_url=ollama, cache_dir=tmp_path)
    assert client.complete_json("s", "u", {}).data["householder"] is True
    assert "think" not in _FakeOllama.requests[-1]


def test_missing_model_gives_pull_instruction(ollama, tmp_path):
    client = OllamaClient(model="missing", base_url=ollama, cache_dir=tmp_path)
    with pytest.raises(LLMUnavailable, match="ollama pull missing"):
        client.complete_json("s", "u", {})


def test_server_down_gives_clear_message(tmp_path):
    client = OllamaClient(base_url="http://127.0.0.1:9", cache_dir=tmp_path, timeout=2)
    with pytest.raises(LLMUnavailable, match="Is it running"):
        client.complete_json("s", "u", {})


def test_offline_mode_never_calls_the_server(tmp_path):
    client = OllamaClient(base_url="http://127.0.0.1:9", cache_dir=tmp_path, offline=True)
    with pytest.raises(LLMUnavailable, match="Offline mode"):
        client.complete_json("s", "u", {})


def test_householder_with_no_recognised_work_is_not_out_of_scope():
    """Regression: all([]) is True, which once marked these as out_of_scope."""
    client = FakeClient(responder({"householder": True, "items": []}))
    res = run_pipeline("some unusual householder works", client)
    assert res.status == "needs_review"
