"""API 业务端点测试: profile/validate/clean/semantic/drift/report + 400 路径.

v1.0.0 曾在这些端点上出现必 500 的调用错误, 本文件作为回归兜底.
"""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from dqengine.api.server import create_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("DQENGINE_API_KEY", raising=False)
    return TestClient(create_app())


@pytest.fixture
def sample_csv(tmp_path):
    df = pd.DataFrame(
        {
            "age": [25, 30, None, 999, 40],
            "email": ["a@x.com", "b@y.com", "c@z.com", "bad", "e@v.com"],
            "city": ["北京", "上海", "北京", "广州", "北京"],
        }
    )
    path = tmp_path / "d.csv"
    df.to_csv(path, index=False)
    return path


def _upload(client, endpoint, path, **kwargs):
    with open(path, "rb") as f:
        return client.post(endpoint, files={"file": (path.name, f)}, **kwargs)


class TestProfileEndpoint:
    def test_profile_ok(self, client, sample_csv):
        resp = _upload(client, "/profile", sample_csv)
        assert resp.status_code == 200
        body = resp.json()
        assert body["profile"]["row_count"] == 5
        assert body["profile"]["column_count"] == 3
        assert "overall_score" in body["score"]
        # 每列画像含空值率
        by_name = {c["column_name"]: c for c in body["profile"]["columns"]}
        assert by_name["age"]["null_count"] == 1

    def test_bad_file_returns_400(self, client, tmp_path):
        bad = tmp_path / "bad.csv"
        bad.write_bytes(b"\x00\x01\x02\xff\xfe not a csv at all")
        resp = _upload(client, "/profile", bad)
        assert resp.status_code == 400
        assert "无法解析上传文件" in resp.json()["detail"]


class TestValidateEndpoint:
    def test_with_uploaded_rules(self, client, sample_csv, tmp_path):
        rules = tmp_path / "r.yaml"
        rules.write_text("columns:\n  age:\n    min: 0\n    max: 100\n", encoding="utf-8")
        with open(sample_csv, "rb") as f, open(rules, "rb") as rf:
            resp = client.post(
                "/validate",
                files={"file": ("d.csv", f), "rules_file": ("r.yaml", rf)},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_rules"] >= 1
        assert body["failed_rules"] >= 1  # 999 越界
        columns_hit = {v["column"] for v in body["violations"]}
        assert "age" in columns_hit

    def test_bad_rules_yaml_400(self, client, sample_csv, tmp_path):
        bad_rules = tmp_path / "bad.yaml"
        bad_rules.write_text("columns: [unclosed", encoding="utf-8")
        with open(sample_csv, "rb") as f, open(bad_rules, "rb") as rf:
            resp = client.post(
                "/validate",
                files={"file": ("d.csv", f), "rules_file": ("bad.yaml", rf)},
            )
        assert resp.status_code == 400
        assert "规则 YAML 语法错误" in resp.json()["detail"]

    def test_non_dict_rules_400(self, client, sample_csv, tmp_path):
        rules = tmp_path / "list.yaml"
        rules.write_text("- just\n- a\n- list\n", encoding="utf-8")
        with open(sample_csv, "rb") as f, open(rules, "rb") as rf:
            resp = client.post(
                "/validate",
                files={"file": ("d.csv", f), "rules_file": ("list.yaml", rf)},
            )
        assert resp.status_code == 400

    def test_missing_rules_400(self, client, sample_csv):
        resp = _upload(client, "/validate", sample_csv)
        assert resp.status_code == 400
        assert "rules_file" in resp.json()["message"]

    def test_rules_path_traversal_blocked(self, client, sample_csv):
        resp = _upload(
            client,
            "/validate",
            sample_csv,
            params={"rules_path": "../../pyproject.toml"},
        )
        assert resp.status_code == 400
        assert "规则目录内" in resp.json()["message"]


class TestCleanEndpoint:
    def test_clean_ok(self, client, sample_csv):
        resp = _upload(client, "/clean", sample_csv)
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["rows_before"] == 5
        assert body["rows_after"] >= 1
        assert "overall_score" in body["score_after"]
        assert set(body["repairs"]) == {
            "missing_values",
            "duplicates",
            "dates_standardized",
            "outliers_found",
        }

    def test_clean_respects_disabled_outlier(self, client, sample_csv, tmp_path):
        """编排器必须尊重清洗配置: outlier.enabled=false 不得删行 (v1.0.0 P0 回归)."""
        cfg = tmp_path / "cfg.yaml"
        cfg.write_text(
            "cleaning:\n"
            "  missing:\n    strategy: mean\n"
            "  outlier:\n    enabled: false\n",
            encoding="utf-8",
        )
        with open(sample_csv, "rb") as f:
            resp = client.post("/clean", files={"file": ("d.csv", f)}, params={"config_path": str(cfg)})
        assert resp.status_code == 200
        body = resp.json()
        assert body["rows_before"] == 5
        # outlier.enabled=false: 999 不得被删 (缺失值填充不删行)
        assert body["rows_after"] == 5
        assert body["repairs"]["outliers_found"] == 0


class TestSemanticEndpoint:
    def test_semantic_ok(self, client, sample_csv):
        resp = _upload(client, "/semantic", sample_csv)
        assert resp.status_code == 200
        body = resp.json()
        assert body["recognized_columns"] == 3
        field_names = {f["column_name"] for f in body["fields"]}
        assert {"age", "email", "city"} <= field_names


class TestDriftEndpoint:
    def test_drift_ok(self, client, tmp_path):
        base = tmp_path / "base.csv"
        cur = tmp_path / "cur.csv"
        pd.DataFrame({"v": [1, 2, 3, 4, 5, 6] * 10}).to_csv(base, index=False)
        pd.DataFrame({"v": [10, 20, 30, 40, 50, 60] * 10}).to_csv(cur, index=False)
        with open(base, "rb") as fb, open(cur, "rb") as fc:
            resp = client.post(
                "/drift", files={"baseline": ("base.csv", fb), "current": ("cur.csv", fc)}
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "baseline_file" in body and "category_drift" in body

    def test_identical_data_no_high_drift(self, client, tmp_path):
        path = tmp_path / "same.csv"
        pd.DataFrame({"v": list(range(50))}).to_csv(path, index=False)
        with open(path, "rb") as f1, open(path, "rb") as f2:
            resp = client.post(
                "/drift", files={"baseline": ("a.csv", f1), "current": ("a.csv", f2)}
            )
        assert resp.status_code == 200
        text = resp.text
        assert '"high"' not in text  # 同分布不应报 high 漂移 (KS p 值门控回归)


class TestReportEndpoint:
    def test_report_html(self, client, sample_csv, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)  # 报告输出目录落在临时目录
        resp = _upload(client, "/report", sample_csv, params={"format": "html"})
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "<!DOCTYPE html" in resp.text or "<html" in resp.text.lower()

    def test_report_json(self, client, sample_csv, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        resp = _upload(client, "/report", sample_csv, params={"format": "json"})
        assert resp.status_code == 200
        body = resp.json()
        assert "column_statistics" in body and "file_path" in body

    def test_report_invalid_format_falls_back(self, client, sample_csv, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        resp = _upload(client, "/report", sample_csv, params={"format": "nope"})
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]


class TestSystemEndpoints:
    def test_root_lists_endpoints(self, client):
        body = client.get("/").json()
        assert body["name"] == "DQEngine API"
        assert "POST /profile" in body["endpoints"]

    def test_health(self, client):
        body = client.get("/health").json()
        assert body["status"] == "healthy"
