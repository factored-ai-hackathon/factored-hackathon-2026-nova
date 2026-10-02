"""The /modelos page shows frontend/src/data/modelMetrics.json: it must match the evaluation files
in ml/ (re-export with ml/export_metrics_page.py after retraining or re-evaluating)."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _exporter():
    spec = importlib.util.spec_from_file_location(
        "export_metrics_page", ROOT / "ml" / "export_metrics_page.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _same(a, b, path="$"):
    """Equal, with floats compared to 1e-3 (the PCA and cosines may differ in the last digit
    between machines)."""
    if isinstance(a, float) or isinstance(b, float):
        assert a == pytest.approx(b, abs=1e-3), path
    elif isinstance(a, dict):
        assert a.keys() == b.keys(), path
        for k in a:
            _same(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list):
        assert len(a) == len(b), path
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            _same(x, y, f"{path}[{i}]")
    else:
        assert a == b, path


def test_metrics_page_data_is_up_to_date():
    exporter = _exporter()
    committed = json.loads(exporter.OUT.read_text(encoding="utf-8"))
    _same(json.loads(exporter.dumps(exporter.build())), committed)


def test_metrics_page_matches_the_reported_numbers():
    data = json.loads(
        (ROOT / "frontend" / "src" / "data" / "modelMetrics.json").read_text(encoding="utf-8")
    )
    intent, rag = data["intent"], data["rag"]
    assert intent["test"]["model"]["macro_f1"] == 0.853
    cells = intent["ablation"]["cells"]
    assert (cells["target_on"]["person"], cells["target_off"]["person"]) == (57, 44)
    hybrid = rag["ranking"]["all"]["hybrid"]
    assert (hybrid["recall@1"]["k"], hybrid["recall@3"]["k"], hybrid["mrr"]) == (33, 37, 0.928)
    # The per-question ranks agree with the aggregate recall.
    answerable = [q for q in rag["test_questions"] if q["gold"]]
    assert sum(q["ranks"]["hybrid"] == 1 for q in answerable) == hybrid["recall@1"]["k"]
    assert sum(q["ranks"]["hybrid"] <= 3 for q in answerable) == hybrid["recall@3"]["k"]
    assert len(rag["chunks"]) == 42
