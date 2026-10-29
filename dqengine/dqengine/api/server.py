"""REST API 服务器 — FastAPI 实现."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
from fastapi import BackgroundTasks, FastAPI, File, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import os

from dqengine import __version__
from dqengine.core.loader import DataLoader
from dqengine.core.profiler import Profiler
from dqengine.core.scorer import QualityScorer
from dqengine.drift.detector import DriftDetector
from dqengine.observability.telemetry import TelemetryManager
from dqengine.models.schemas import (
    APIResponse,
)
from dqengine.repair.date_standardizer import DateStandardizer
from dqengine.repair.duplicate import DuplicateCleaner
from dqengine.repair.missing_value import MissingValueCleaner
from dqengine.repair.outlier import OutlierDetector
from dqengine.report.advanced_generator import AdvancedReportGenerator
from dqengine.rules.validator import RuleValidator
from dqengine.utils.logger import get_logger
from dqengine.semantic.detector import SemanticDetector

logger = get_logger(__name__)


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
        # 通配 Origin 下开启凭据等于允许任意网站携凭据跨域调用
        # (Starlette 会显式回显请求 Origin 并附带 Allow-Credentials),
        # 本服务无 Cookie 会话, 必须关闭
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    loader = DataLoader()
    profiler = Profiler()
    scorer = QualityScorer()
    validator = RuleValidator()
    detector = SemanticDetector()
    drift_detector = DriftDetector()
    telemetry = TelemetryManager(db_path="dqengine_telemetry.db")

    # ---- 可选 API Key 鉴权 ----
    # 设置环境变量 DQENGINE_API_KEY 后, 除健康检查/文档/指标外的所有
    # 端点都要求请求头 X-API-Key; 未设置时保持开放 (本地/内网开发模式),
    # 启动日志会明确提示当前模式
    api_key = os.environ.get("DQENGINE_API_KEY")

    @app.middleware("http")
    async def api_key_auth(request: Request, call_next):
        open_paths = {"/", "/health", "/docs", "/redoc", "/openapi.json", "/metrics"}
        if api_key and request.url.path not in open_paths:
            if request.headers.get("X-API-Key") != api_key:
                return JSONResponse(
                    content={"success": False, "message": "无效的 API Key"},
                    status_code=401,
                )
        return await call_next(request)

    logger.warning(
        "API 鉴权模式: %s (通过环境变量 DQENGINE_API_KEY 配置)",
        "已启用" if api_key else "未启用 —— 请勿将无鉴权实例暴露到公网",
    )

    @app.get("/metrics", tags=["系统"])
    async def metrics() -> Response:
        """Prometheus 指标端点."""
        return Response(content=telemetry.export_prometheus(), media_type="text/plain; version=0.0.4")

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
                "GET /metrics",
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
        rules_path: Optional[str] = Query(
            None,
            description="服务器端 YAML 规则路径 (仅允许规则目录内的文件, 默认 ./configs)",
        ),
    ) -> JSONResponse:
        """上传数据文件并执行规则验证."""
        df = await _read_uploaded_file(file)

        if rules_file:
            import yaml

            content = await rules_file.read()
            parsed = yaml.safe_load(content)
            if not isinstance(parsed, dict):
                return JSONResponse(
                    content=APIResponse(
                        success=False,
                        message="规则文件格式错误: 应为包含 columns 键的 YAML 字典",
                    ).model_dump(),
                    status_code=400,
                )
            rules = validator._parse_rules(parsed)
        elif rules_path:
            # 限制在规则目录内, 防止未认证客户端用任意路径探测/读取服务器文件
            rules_dir = Path("configs").resolve()
            candidate = Path(rules_path)
            resolved = candidate if candidate.is_absolute() else (rules_dir / candidate)
            try:
                resolved = resolved.resolve()
                resolved.relative_to(rules_dir)
            except ValueError:
                return JSONResponse(
                    content=APIResponse(
                        success=False,
                        message=f"rules_path 必须位于规则目录内: {rules_dir}",
                    ).model_dump(),
                    status_code=400,
                )
            rules = str(resolved)
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

        # 内存直读: 此前 to_csv 落盘再 read_csv 读回, 每请求多付
        # 两次完整序列化 + 两次解析 (1M 行量级约 6s 纯磁盘 I/O);
        # 临时文件泄漏路径随落盘逻辑一并消除
        report = drift_detector.detect_frames(
            baseline_df,
            current_df,
            baseline_name=baseline.filename or "baseline",
            current_name=current.filename or "current",
        )

        return JSONResponse(content=report.model_dump())

    # ---- 报告生成 ----

    @app.post("/report", tags=["报告"])
    async def report_endpoint(
        file: UploadFile = File(...),
        format: str = Query("html", description="报告格式: html, json, markdown"),
    ) -> Response:
        """上传数据文件并生成质量报告."""
        df = await _read_uploaded_file(file)
        report_gen = AdvancedReportGenerator()

        from dqengine.models.schemas import ReportFormat

        fmt_map = {"html": ReportFormat.HTML, "json": ReportFormat.JSON, "markdown": ReportFormat.MARKDOWN}
        report_fmt = fmt_map.get(format, ReportFormat.HTML)

        profile = profiler.profile(df, file_path=file.filename or "data")
        score = scorer.score(df, profile)
        paths = report_gen.generate(
            profile=profile,
            score=score,
            repairs=[],
            outliers=[],
            df=df,
            formats=[report_fmt],
        )
        content = paths[0].read_text(encoding="utf-8")

        media_types = {
            "html": "text/html",
            "json": "application/json",
            "markdown": "text/markdown",
        }
        return Response(content=content, media_type=media_types.get(format, "text/html"))

    async def _read_uploaded_file(file: UploadFile) -> pd.DataFrame:
        """读取上传文件为 DataFrame (内存直读, 免临时落盘往返)."""
        content = await file.read()
        file_name = file.filename or "data.csv"
        return loader.load_bytes(content, file_name)

    return app
