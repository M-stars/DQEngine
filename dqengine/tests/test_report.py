"""report/ 模块回归测试: HTML/JSON/Markdown 三格式生成 + XSS 转义."""

import json

import pandas as pd
import pytest

from dqengine.core.profiler import Profiler
from dqengine.core.scorer import QualityScorer
from dqengine.models.schemas import ReportFormat
from dqengine.report.advanced_generator import AdvancedReportGenerator
from dqengine.report.generator import ReportGenerator


@pytest.fixture
def profile_and_score(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    df = pd.DataFrame(
        {
            "age": [25, 30, None, 40, 999],
            "name": ["a", "b", "c", "d", "e"],
        }
    )
    profiler = Profiler()
    profile = profiler.profile(df, file_path="t.csv")
    score = QualityScorer().score(df, profile)
    return profile, score


class TestBasicReportGenerator:
    def test_html_report_written(self, profile_and_score, tmp_path):
        profile, score = profile_and_score
        out = tmp_path / "report.html"
        path = ReportGenerator().generate(profile, score, [], [], output_path=out)
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "<html" in content.lower() or "<!doctype" in content.lower()

    def test_column_names_html_escaped(self, tmp_path, monkeypatch):
        """P0 回归: 用户可控列名/路径必须 HTML 转义, 不得出现可执行 script 注入."""
        monkeypatch.chdir(tmp_path)
        evil_col = "<script>alert(1)</script>"
        df = pd.DataFrame({evil_col: [1, 2, 3]})
        profiler = Profiler()
        profile = profiler.profile(df, file_path="evil.csv")
        score = QualityScorer().score(df, profile)
        out = tmp_path / "xss.html"
        ReportGenerator().generate(profile, score, [], [], output_path=out)
        content = out.read_text(encoding="utf-8")
        assert "<script>alert(1)</script>" not in content
        assert "&lt;script&gt;" in content


class TestAdvancedReportGenerator:
    def test_all_formats(self, profile_and_score, tmp_path):
        profile, score = profile_and_score
        paths = AdvancedReportGenerator().generate(
            profile=profile, score=score, repairs=[], outliers=[]
        )
        assert len(paths) == 3
        suffixes = {p.suffix for p in paths}
        assert {".html", ".json", ".md"} <= suffixes
        for p in paths:
            assert p.exists()

    def test_html_only(self, profile_and_score, tmp_path):
        profile, score = profile_and_score
        paths = AdvancedReportGenerator().generate(
            profile=profile,
            score=score,
            repairs=[],
            outliers=[],
            formats=[ReportFormat.HTML],
        )
        assert len(paths) == 1
        assert paths[0].suffix == ".html"

    def test_json_report_parseable(self, profile_and_score, tmp_path):
        profile, score = profile_and_score
        paths = AdvancedReportGenerator().generate(
            profile=profile,
            score=score,
            repairs=[],
            outliers=[],
            formats=[ReportFormat.JSON],
        )
        body = json.loads(paths[0].read_text(encoding="utf-8"))
        assert isinstance(body, dict)

    def test_xss_escaped_in_html(self, tmp_path, monkeypatch):
        """P0 回归: 高级报告同样必须转义用户列名."""
        monkeypatch.chdir(tmp_path)
        df = pd.DataFrame({"<img src=x onerror=alert(1)>": [1.0, 2.0, 3.0]})
        profiler = Profiler()
        profile = profiler.profile(df, file_path="x.csv")
        score = QualityScorer().score(df, profile)
        paths = AdvancedReportGenerator().generate(
            profile=profile,
            score=score,
            repairs=[],
            outliers=[],
            formats=[ReportFormat.HTML],
        )
        content = paths[0].read_text(encoding="utf-8")
        assert "<img src=x onerror=alert(1)>" not in content
