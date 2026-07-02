"""Tests for the FDH API index generator (deterministic, no network)."""
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "fdh" / "build_api_index.py"
SPEC = REPO / "context" / "full-fdh-openapi-spec.yaml"
INDEX = REPO / "context" / "fdh_api_index.json"

REQUIRED_KEYS = {
    "path", "method", "operation_id", "summary", "category",
    "primary_entities", "intent_patterns", "llm_hint", "yaml_lines",
}


def test_generator_runs_and_writes_index():
    result = subprocess.run(
        ["uv", "run", "--script", str(SCRIPT)],
        capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert INDEX.exists()


def test_index_shape_and_known_ops():
    data = json.loads(INDEX.read_text())
    assert isinstance(data, list) and len(data) >= 100
    keyset = {(e["path"], e["method"]) for e in data}
    for e in data:
        assert REQUIRED_KEYS <= set(e), f"missing keys in {e.get('path')}"
        start, end = e["yaml_lines"]
        assert isinstance(start, int) and isinstance(end, int)
        assert 0 < start <= end
    # GET /samples/{id} (operationId readSample) is definitely present:
    assert ("/samples/{id}", "GET") in keyset
    read = next(e for e in data if e["path"] == "/samples/{id}" and e["method"] == "GET")
    assert read["category"] == "samples_read"
    assert "samples" in read["primary_entities"]
    # every DELETE op is flagged destructive:
    deletes = [e for e in data if e["method"] == "DELETE"]
    assert deletes, "spec has DELETE operations"
    for e in deletes:
        assert e["category"].endswith("_delete")
        assert "DESTRUCTIVE" in e["llm_hint"]


def test_yaml_lines_point_at_the_operation():
    data = json.loads(INDEX.read_text())
    spec_lines = SPEC.read_text().splitlines()
    e = next(x for x in data if x["path"] == "/samples/{id}" and x["method"] == "GET")
    start, end = e["yaml_lines"]
    assert 1 <= start <= end <= len(spec_lines)
    slice_text = "\n".join(spec_lines[start - 1:end])
    assert "operationId: readSample" in slice_text
