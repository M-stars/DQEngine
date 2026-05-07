# DQEngine API 文档

启动 API 服务: `dq serve`

## 端点列表

| Method | Path | 描述 |
|--------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/` | API 信息 |
| POST | `/profile` | 数据画像 |
| POST | `/validate` | 规则验证 |
| POST | `/clean` | 自动清洗 |
| POST | `/semantic` | 语义分析 |
| POST | `/drift` | 漂移检测 |
| POST | `/report` | 报告生成 |

## 交互式文档

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 请求示例

### POST /profile

```bash
curl -X POST http://localhost:8000/profile \
  -F "file=@data.csv"
```

### POST /validate

```bash
curl -X POST http://localhost:8000/validate \
  -F "file=@data.csv" \
  -F "rules_file=@rules.yaml"
```

### POST /clean

```bash
curl -X POST http://localhost:8000/clean \
  -F "file=@data.csv"
```

### POST /drift

```bash
curl -X POST http://localhost:8000/drift \
  -F "baseline=@baseline.csv" \
  -F "current=@current.csv"
```

### POST /semantic

```bash
curl -X POST http://localhost:8000/semantic \
  -F "file=@data.csv"
```

### POST /report

```bash
curl -X POST "http://localhost:8000/report?format=html" \
  -F "file=@data.csv"
```

## 响应格式

所有端点返回 JSON，格式为 Pydantic 模型序列化结果。

```json
{
  "success": true,
  "message": "",
  "data": {}
}
```
