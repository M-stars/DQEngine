"""REST API 服务器 — FastAPI 实现."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from dqengine import __version__
from dqengine.core.loader import DataLoader
from dqengine.core.profiler import Profiler
from dqengine.core.scorer import QualityScorer
from dqengine.drift.detector import DriftDetector
from dqengine.models.schemas import (
    APIResponse,
    CleanRequest,
    DriftReport,
    DriftRequest,
    ProfileRequest,
    ValidateRequest,
)
from dqengine.repair.date_standardizer import DateStandardizer
from dqengine.repair.duplicate import DuplicateCleaner
from dqengine.repair.missing_value import MissingValueCleaner
from dqengine.repair.outlier import OutlierDetector
from dqengine.report.advanced_generator import AdvancedReportGenerator
from dqengine.rules.validator import RuleValidator
from dqengine.semantic.detector import SemanticDetector


def create_app() -> FastAPI:
    """创建 FastAPI 应用."""

    app = FastAPI(
        title="DQEngine API",
        description="AI-Driven Data Quality Platform — 数据质量智能分析平台",
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    loader = DataLoader()
    profiler = Profiler()
    scorer = QualityScorer()
    validator = RuleValidator()
    detector = SemanticDetector()
    drift_detector = DriftDetector()

    # ---- 健康检查 ----

    @app.get("/health", tags=["系统"])
    async def health() -> Dict[str, str]:
        return {"status": "healthy", "version": __version__}

    @app.get("/", tags=["系统"])
    async def root() -> Dict[str, Any]:
        return {
            "name": "DQEngine API",
            "version": __version__,
            "docs": "/docs",
            "endpoints": [
                "POST /profile",
                "POST /validate",
                "POST /clean",
                "POST /semantic",
                "POST /drift",
                "GET /health",
            ],
        }

    # ---- 数据画像 ----

    @app.post("/profile", tags=["数据分析"])
    async def profile_endpoint(
        file: UploadFile = File(...),
        background_tasks: BackgroundTasks = BackgroundTasks(),
    ) -> JSONResponse:
        """上传数据文件并返回字段画像."""
        df = await _read_uploaded_file(file)
        result = profiler.profile(df, file_path=file.filename or "upload")
        score = scorer.score(df, result)
        return JSONResponse(
            content={
                "profile": result.model_dump(),
                "score": score.model_dump(),
            }
        )

    # ---- 规则验证 ----

    @app.post("/validate", tags=["规则验证"])
    async def validate_endpoint(
        file: UploadFile = File(...),
        rules_file: Optional[UploadFile] = File(None),
        rules_path: Optional[str] = Query(None, description="服务器端 YAML 规则路径"),
    ) -> JSONResponse:
        """上传数据文件并执行规则验证."""
        df = await _read_uploaded_file(file)

        if rules_file:
            import yaml

            content = await rules_file.read()
            rules = yaml.safe_load(content)
        elif rules_path:
            rules = rules_path
        else:
            return JSONResponse(
                content=APIResponse(
                    success=False,
                    message="请提供 rules_file (上传) 或 rules_path (服务器路径)",
                ).model_dump(),
                status_code=400,
            )

        result = validator.validate(df, rules)
        return JSONResponse(content=result.model_dump())

    # ---- 自动清洗 ----

    @app.post("/clean", tags=["数据清洗"])
    async def clean_endpoint(
        file: UploadFile = File(...),
        config_path: Optional[str] = Query(None),
    ) -> JSONResponse:
        """上传数据文件并执行自动清洗."""
        df = await _read_uploaded_file(file)
        rows_before = len(df)

        # 执行清洗步骤
        missing_cleaner = MissingValueCleaner()
        dup_cleaner = DuplicateCleaner()
        date_std = DateStandardizer()
        outlier_detector = OutlierDetector()

        df, repair1 = missing_cleaner.clean(df)
        df, repair2 = dup_cleaner.clean(df)
        df, report3 = date_std.standardize(df)
        outliers = outlier_detector.detect(df)

        score_after = scorer.score(df, profiler.profile(df))
        rows_after = len(df)

        return JSONResponse(
            content={
                "success": True,
                "rows_before": rows_before,
                "rows_after": rows_after,
                "score_after": score_after.model_dump(),
                "repairs": {
                    "missing_values": repair1.model_dump(),
                    "duplicates": repair2.model_dump(),
                    "dates_standardized": report3.model_dump(),
                    "outliers_found": len(outliers),
                },
            }
        )

    # ---- 语义分析 ----

    @app.post("/semantic", tags=["语义分析"])
    async def semantic_endpoint(
        file: UploadFile = File(...),
    ) -> JSONResponse:
        """上传数据文件并执行语义分析."""
        df = await _read_uploaded_file(file)
        result = detector.detect(df, file_path=file.filename or "upload")
        return JSONResponse(content=result.model_dump())

    # ---- 漂移检测 ----

    @app.post("/drift", tags=["漂移检测"])
    async def drift_endpoint(
        baseline: UploadFile = File(...),
        current: UploadFile = File(...),
    ) -> JSONResponse:
        """上传基线和当前数据文件，执行漂移检测."""
        baseline_df = await _read_uploaded_file(baseline)
        current_df = await _read_uploaded_file(current)

        # 保存临时文件用于漂移检测
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as bf, \
             tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as cf:
            baseline_df.to_csv(bf.name, index=False)
            current_df.to_csv(cf.name, index=False)
            report = drift_detector.detect(bf.name, cf.name)
            Path(bf.name).unlink(missing_ok=True)
            Path(cf.name).unlink(missing_ok=True)

        return JSONResponse(content=report.model_dump())

    # ---- 报告生成 ----

    @app.post("/report", tags=["报告"])
    async def report_endpoint(
        file: UploadFile = File(...),
        format: str = Query("html", description="报告格式: html, json, markdown"),
    ) -> HTMLResponse:
        """上传数据文件并生成质量报告."""
        df = await _read_uploaded_file(file)
        report_gen = AdvancedReportGenerator()

        from dqengine.models.schemas import ReportFormat

        fmt_map = {"html": ReportFormat.HTML, "json": ReportFormat.JSON, "markdown": ReportFormat.MARKDOWN}
        report_fmt = fmt_map.get(format, ReportFormat.HTML)

        with tempfile.NamedTemporaryFile(suffix=f".{format}", delete=False) as tmp:
            report_gen.generate(df, file.filename or "data", str(Path(tmp.name)), report_fmt)
            content = Path(tmp.name).read_text(encoding="utf-8")
            Path(tmp.name).unlink(missing_ok=True)

        media_types = {
            "html": "text/html",
            "json": "application/json",
            "markdown": "text/markdown",
        }
        return HTMLResponse(content=content, media_type=media_types.get(format, "text/html"))

    async def _read_uploaded_file(file: UploadFile) -> pd.DataFrame:
        """读取上传文件为 DataFrame."""
        content = await file.read()
        suffix = Path(file.filename or "data.csv").suffix.lower()

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            df = loader.load(Path(tmp_path))
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        return df

    return app
