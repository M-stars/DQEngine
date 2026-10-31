"""CLI 命令回归测试: 主要命令的 CliRunner 离线路径.

覆盖 15 个命令中的核心 10 个 (serve/schedule/monitor 常驻型与
stream_validate 已由 test_production/test_realtime 覆盖的不在此重复).
"""

import json

import pandas as pd
import pytest
from typer.testing import CliRunner

from dqengine.cli.commands import app

runner = CliRunner()


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """隔离 cwd, 避免 CLI 输出文件污染仓库根目录."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def clean_csv(workdir):
    path = workdir / "clean.csv"
    pd.DataFrame(
        {
            "age": [25, 30, 35, 40, 45],
            "email": ["a@x.com", "b@y.com", "c@z.com", "d@w.com", "e@v.com"],
        }
    ).to_csv(path, index=False)
    return path


@pytest.fixture
def dirty_csv(workdir):
    path = workdir / "dirty.csv"
    pd.DataFrame(
        {
            "age": [25, None, 35, None, 999],
            "email": ["a@x.com", None, "c@z.com", "d@w.com", "e@v.com"],
            "city": ["北京", "北京", "上海", "上海", "广州"],
        }
    ).to_csv(path, index=False)
    return path


@pytest.fixture
def rules_yaml(workdir):
    path = workdir / "rules.yaml"
    path.write_text(
        "columns:\n  age:\n    min: 0\n    max: 100\n    not_null: true\n",
        encoding="utf-8",
    )
    return path


# ---- version ----


class TestVersion:
    def test_version_shows(self):
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "DQEngine" in result.output


# ---- profile ----


class TestProfile:
    def test_profile_ok(self, clean_csv):
        result = runner.invoke(app, ["profile", str(clean_csv)])
        assert result.exit_code == 0, result.output
        assert "age" in result.output

    def test_profile_save_json(self, clean_csv, workdir):
        out = workdir / "profile.json"
        result = runner.invoke(app, ["profile", str(clean_csv), "-o", str(out)])
        assert result.exit_code == 0, result.output
        saved = json.loads(out.read_text(encoding="utf-8"))
        assert saved["row_count"] == 5

    def test_profile_missing_file(self, workdir):
        result = runner.invoke(app, ["profile", "no_such.csv"])
        assert result.exit_code == 1


# ---- auto ----


class TestAuto:
    def test_auto_clean_and_report(self, dirty_csv, workdir):
        out = workdir / "out.csv"
        report = workdir / "r.html"
        result = runner.invoke(
            app, ["auto", str(dirty_csv), "-o", str(out), "-r", str(report)]
        )
        assert result.exit_code == 0, result.output
        assert out.exists()
        assert report.exists()
        cleaned = pd.read_csv(out)
        # 缺失被填充, 行数不因缺失策略 drop 而减少 (mean 填充)
        assert len(cleaned) == 5

    def test_auto_missing_file(self, workdir):
        result = runner.invoke(app, ["auto", "no_such.csv"])
        assert result.exit_code == 1


# ---- validate ----


class TestValidate:
    def test_validate_pass(self, clean_csv, rules_yaml):
        result = runner.invoke(app, ["validate", str(clean_csv), "-r", str(rules_yaml)])
        assert result.exit_code == 0, result.output

    def test_validate_violations_json_exit_1(self, dirty_csv, rules_yaml):
        result = runner.invoke(
            app, ["validate", str(dirty_csv), "-r", str(rules_yaml), "--json"]
        )
        assert result.exit_code == 1  # 有违规退出码 1 (CI 门禁约定)
        body = json.loads(result.output)
        assert body["failed_rules"] >= 1

    def test_validate_missing_rules_file(self, clean_csv, workdir):
        result = runner.invoke(app, ["validate", str(clean_csv), "-r", "no_rules.yaml"])
        assert result.exit_code == 1


# ---- semantic ----


class TestSemantic:
    def test_semantic_ok(self, clean_csv):
        result = runner.invoke(app, ["semantic", str(clean_csv)])
        assert result.exit_code == 0, result.output
        assert "email" in result.output


# ---- drift ----


class TestDrift:
    def test_drift_ok(self, workdir):
        base = workdir / "base.csv"
        cur = workdir / "cur.csv"
        pd.DataFrame({"v": list(range(40))}).to_csv(base, index=False)
        pd.DataFrame({"v": [x * 10 for x in range(40)]}).to_csv(cur, index=False)
        out = workdir / "drift.json"
        result = runner.invoke(
            app, ["drift", str(base), str(cur), "-o", str(out)]
        )
        assert result.exit_code == 0, result.output
        saved = json.loads(out.read_text(encoding="utf-8"))
        assert "baseline_file" in saved

    def test_drift_missing_baseline(self, workdir, clean_csv):
        result = runner.invoke(app, ["drift", "no_base.csv", str(clean_csv)])
        assert result.exit_code == 1


# ---- batch ----


class TestBatch:
    def test_batch_processes_directory(self, dirty_csv, clean_csv, workdir):
        data_dir = workdir / "data"
        data_dir.mkdir()
        (data_dir / "a.csv").write_text(dirty_csv.read_text(encoding="utf-8"), encoding="utf-8")
        (data_dir / "b.csv").write_text(clean_csv.read_text(encoding="utf-8"), encoding="utf-8")
        out_dir = workdir / "batch_out"
        result = runner.invoke(app, ["batch", str(data_dir), "-o", str(out_dir)])
        assert result.exit_code == 0, result.output
        outputs = list(out_dir.glob("*.csv"))
        assert len(outputs) == 2

    def test_batch_missing_directory(self, workdir):
        result = runner.invoke(app, ["batch", "no_dir"])
        assert result.exit_code == 1


# ---- plugins / doctor / pipeline ----


class TestIntrospection:
    def test_plugins_lists_types(self):
        result = runner.invoke(app, ["plugins"])
        assert result.exit_code == 0, result.output

    def test_plugins_filtered(self):
        result = runner.invoke(app, ["plugins", "-t", "validator"])
        assert result.exit_code == 0, result.output

    def test_doctor_ok(self):
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0, result.output

    def test_pipeline_generated_script(self, dirty_csv, workdir):
        out = workdir / "gen_pipeline.py"
        result = runner.invoke(app, ["pipeline", str(dirty_csv), "-o", str(out)])
        assert result.exit_code == 0, result.output
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        # 生成脚本必须可编译 (v1.0.0 曾出现 Windows 路径 SyntaxError 与列名注入)
        compile(content, str(out), "exec")
