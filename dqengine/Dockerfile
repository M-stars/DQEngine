# DQEngine Dockerfile
# AI-Driven Data Quality Platform
FROM python:3.11-slim

LABEL org.opencontainers.image.title="DQEngine"
LABEL org.opencontainers.image.description="AI-Driven Data Quality Platform"
LABEL org.opencontainers.image.version="0.3.0"

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制并安装 Python 依赖
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir -e ".[all]"

# 复制应用代码
COPY dqengine/ ./dqengine/
COPY configs/ ./configs/
COPY examples/ ./examples/

# 安装项目
RUN pip install -e ".[all]"

# 创建必要的目录
RUN mkdir -p /data /reports /logs

# 暴露 API 端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 默认启动 API 服务
ENTRYPOINT ["dq"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
