# 运镜控制后端项目

这是一个用于教学与原型验证的运镜控制后端（Flask + pybullet 模拟）。仓库包含模拟控制、简单持久层、健康检查、统一错误处理等模块。

## 快速开始

- 启动服务：`python main.py`（开发服务器，仅用于调试）
- 健康检查：`GET /api/v1/test` 或 `GET /api/v1/health`

## 错误响应（摘要）

详细规范见 `API_ERRORS.md`（包含示例响应与调试说明）。

错误响应采用统一封装，主要格式为：

```
{
  "code": <http-status-code>,
  "msg": "<human readable message>",
  "data": { ... },
  "error": { ... }    # 向后兼容
}
```

- `code`：HTTP 状态码
- `msg`：简短描述
- `data`：结构化字段，包含 `request_id`、`type`、`timestamp`、`details`、以及在 DEBUG 下可选的 `trace`
- `error`：向后兼容对象（保留给旧客户端/测试）

后端会在响应头 `X-Request-ID` 中回传请求 ID，若客户端已提供同名 header 则复用该值。

更多细节、示例以及调试命令请参阅：`API_ERRORS.md`。

## 开发提示

- 若要临时降低随机碰撞触发以便调试，可在启动环境中设置：
  - Windows PowerShell：`$env:DEV_LOW_COLLISIONS='1'; python main.py`
- 单元测试：`python -m unittest discover -s tests -p "test_*.py" -v`

---

如果你希望我把 README 的错误响应节进一步扩展为英文版或把完整内容直接嵌入 README，请告诉我，我将继续编辑。
