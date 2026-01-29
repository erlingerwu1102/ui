**API 错误响应规范**

本文档说明后端统一化的错误响应格式、调试字段及如何在客户端/测试中使用请求追踪 ID。

1) 响应总体结构

所有 API 错误响应采用兼容封装：

```
{
  "code": <http-status-code>,
  "msg": "<human readable message>",
  "data": { ... },
  "error": { ... }    # 兼容旧客户端（可选）
}
```

- `code`：HTTP 状态码（整数），同时做为应用级错误码的入口。
- `msg`：简短的人类可读错误信息。
- `data`：结构化附加信息，包含 `request_id`、`type`（错误类别）、`timestamp`，以及 `details` 和可选 `trace`（仅 DEBUG 时返回）。
- `error`：向后兼容字段，保留了旧版接口使用的 `error` 对象（包含 `type`/`message`/`code`/`request_id`/`timestamp`/`details` 等），以免破坏现有客户端或单元测试。

2) 常见示例

- APIException（客户端可控的业务错误，例如参数错误）：

```
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json
X-Request-ID: 1a2b3c

{
  "code": 422,
  "msg": "invalid input",
  "data": {
    "request_id": "1a2b3c",
    "type": "APIException",
    "timestamp": 1764053258,
    "details": { "field": "x" }
  },
  "error": {
    "type": "APIException",
    "message": "invalid input",
    "code": 422,
    "request_id": "1a2b3c",
    "timestamp": 1764053258,
    "details": { "field": "x" }
  }
}
```

- InternalError（服务器未处理异常，DEBUG 为 false 时不返回堆栈）

```
HTTP/1.1 500 Internal Server Error
Content-Type: application/json
X-Request-ID: aabb-ccdd

{
  "code": 500,
  "msg": "An internal error occurred",
  "data": {
    "request_id": "aabb-ccdd",
    "type": "InternalError",
    "timestamp": 1764054000
  },
  "error": { ... }
}
```

如果服务在 `DEBUG` 模式下，会在 `data.trace` 与 `error.trace` 中返回简短的 traceback 字符串，便于本地调试——生产环境请勿开启。

3) 请求追踪（X-Request-ID）

- 后端会在响应头 `X-Request-ID` 中回传用于链路追踪的 ID。如果客户端在请求头中带上 `X-Request-ID`，后端会复用该值；否则后端会生成 UUID 并同时在响应头与 `data.request_id` 中返回。

4) 客户端/自动化测试使用建议

- 在集成测试或前端调用中，建议：
  - 检查 HTTP 状态码 `code`；
  - 解析 `data.request_id` 并在日志/错误报告中附带；
  - 在断言或错误处理时优先使用 `data.type`（例如 `APIException`/`ValidationError`/`InternalError`）；
  - 若 `data.trace` 存在（DEBUG），仅用于开发排查，切勿将其写入生产日志外部可见位置。

5) 调试与演示命令示例（PowerShell）

获取状态并查看 request_id：

```powershell
Invoke-RestMethod -Uri 'http://localhost:8000/api/v1/test' -Method Get | ConvertTo-Json -Depth 4
```

触发参数错误示例：

```powershell
$body = @{ x_offset = 'not-a-number' } | ConvertTo-Json
Invoke-RestMethod -Uri 'http://localhost:8000/api/v1/translate' -Method Post -Body $body -ContentType 'application/json' -ErrorAction SilentlyContinue | ConvertTo-Json -Depth 4
```

6) 变更记录 / 注意事项

- 该项目同时保留了 `error` 字段以兼容历史客户端；新客户端建议遵循 `code/msg/data` 主封装。
- 在 CI/生产中请保持 `DEBUG=False`，以避免泄露堆栈信息。
- 如果需要把 `request_id` 与日志系统（如 ELK/Seq）关联，请在应用接入处确保 `X-Request-ID` 被记录到 access log。

---

