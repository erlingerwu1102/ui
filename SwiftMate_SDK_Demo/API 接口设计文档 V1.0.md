# RESTful API 接口设计文档 V1.0

## 服务与版本信息
- 服务名称：SwiftMate 运镜控制API
- 文档版本：1.0（兼容并衔接 V2.0 规范）
- 基础路径：/api（V1 完整路径为 /api/v1）
- 支持协议：HTTP/HTTPS

## 接口概述
- Base URL 示例：http://localhost:8000/api/v1
- 数据格式：请求/响应均为 JSON
- 状态码：200（成功）、400（参数错误）、500（服务器错误）

## V1 测试接口
- 路径：GET /api/1/test
- 功能：测试 API 可用性与版本兼容性
- 响应示例：
```json
{
  "code": 200,
  "msg": "API路由测试成功",
  "data": {
    "service": "运镜控制API",
    "version": "1.0",
    "motion_control_available": true,
    "support": true,
    "base_url": "/api"
  }
}

## V2 决赛版接口（已移植自 SDK Demo）

本项目已移植 SDK Demo 中的 V2 关键接口，位于基础路径 `/api/v2`，包含：

- `GET /api/v2/test`：V2 版本健康/能力声明
- `POST /api/v2/trajectory/multi-segment`：多段运镜拼接（支持 `linear` / `bezier` 插值）
  - 请求示例：
    ```json
    {
      "waypoints": [[0.4,0.4,0.3],[0.8,0.4,0.3],[0.8,0.7,0.3]],
      "interpolation_type": "bezier",
      "duration": 8.0
    }
    ```
- `POST /api/v2/trajectory/preset/circle`：环绕运镜预设（中心点、半径、时长）
- `POST /api/v2/trajectory/preset/push-pull`：推拉运镜预设（方向、距离、时长）
- `GET /api/v2/task/status?task_id=...`：任务状态查询（running/finished/not_found）
- `POST /api/v2/task/cancel`：任务取消（请求体 `{ "task_id": "..." }`）

- 动力学辨识相关（V2 辅助接口）
  - `POST /api/v2/dynamics/identification/set-params`：设置辨识参数
  - `POST /api/v2/dynamics/identification/confirm-zero`：确认零点位置
  - `POST /api/v2/dynamics/identification/test-safety`：轨迹安全测试
  - `POST /api/v2/dynamics/identification/start`：开始辨识
  - `POST /api/v2/dynamics/identification/stop`：停止辨识
  - `GET /api/v2/dynamics/identification/status`：查询辨识状态

- 力矩前馈与碰撞灵敏度
  - `POST /api/v2/torque/feedforward/enable`：启用/禁用力矩前馈（`{ "enabled": true }`）
  - `POST /api/v2/torque/feedforward/update-params`：更新动力学参数（mass/inertia/friction，各6项）
  - `POST /api/v2/collision/sensitivity`：设置单轴碰撞灵敏度

- 坐标系与关节控制
  - `POST /api/v2/coordinate/switch`：切换坐标系（joint/cartesian/tool/user）
  - `POST /api/v2/joint/move-single`：单轴关节运动（`joint_id`, `target_angle`, `speed`）
  - `POST /api/v2/joint/move-all`：同步控制全部关节（6个角度）

- 决赛推荐配置
  - `GET /api/v2/final/recommend`：返回演示时推荐的调用组合与参数

说明：所有 V2 接口在本仓库中已使用降级兼容策略实现——在 `motion_control` 中若缺失某些高级函数（例如 `preset_circle_motion`），路由会使用可用的基础接口或简单模拟在后台运行，以保证 API 可用性并便于本地测试。

```

## 认证与速率限制（Auth & Rate Limiting）

以下内容描述了本服务中用于保护敏感接口的认证机制与进程内速率限制的行为，并给出常用的配置与示例命令。

- 验证行为：
  - 受保护的路由使用进程内装饰器 `require_api_key`（定义于 `app/routes.py`），验证来源于三处的 API key：
    1. `Authorization: Bearer <API_KEY>` HTTP 头
    2. `X-API-Key` HTTP 头
    3. 查询参数 `?api_key=...`
  - 验证逻辑基于全局配置实例 `robot_config.allowed_api_keys`（定义于 `robot_config.py`）。仅当 `robot_config.validate_api_key(key)` 返回 `True` 时，调用才会被允许。
  - 注意：出于安全与现场救援需要，紧急停止（emergency stop）接口保持匿名可调用（不受 API key 验证限制）。请确保物理急停（硬件 E-Stop）部署在现场。

- 速率限制（防高频指令）：
  - 实现在 `app/routes.py`，为进程内按客户端 IP 的简单速率限制：变量名为 `_min_cmd_interval`，含义为两次受保护 API 请求之间的最小秒数间隔。
  - 默认值：`_min_cmd_interval = 0.05`（50 毫秒）。当来自同一 IP 的请求间隔小于该值时，服务器返回 HTTP 429 `Too Many Requests`。
  - 实现为内存计时（`_last_cmd_time` 字典），仅适用于单实例部署；若在多实例或生产环境使用，请改用集中式速率限制（如 Redis 令牌桶或 NGINX 限速）以保证一致性。

配置与示例命令
- 在 Python 运行时动态添加/移除 API key（便于调试或临时测试）：

  - 使用项目的 Python（推荐在已激活的虚拟环境中运行）：

    Bash / CMD:
    ```bash
    python -c "from robot_config import robot_config; robot_config.add_api_key('demo-key-123'); print('added')"
    python -c "from robot_config import robot_config; robot_config.remove_api_key('demo-key-123'); print('removed')"
    ```

    PowerShell (已启用虚拟环境示例)：
    ```powershell
    & .\.venv\Scripts\python.exe -c "from robot_config import robot_config; robot_config.add_api_key('demo-key-123'); print('added')"
    & .\.venv\Scripts\python.exe -c "from robot_config import robot_config; robot_config.remove_api_key('demo-key-123'); print('removed')"
    ```

  - 说明：上述命令直接修改进程内的 `robot_config` 实例（对当前运行的进程生效）。若要生效到正在运行的 Flask 服务器，请在服务器进程内部执行等效操作（例如在管理脚本或交互式控制台中运行）。持久化方式请把初始密钥写入部署脚本或系统环境变量，并在应用启动时注入到 `robot_config.allowed_api_keys`。

- 使用 API key 进行请求（示例）：

  - curl（Bearer header）：
    ```bash
    curl -H "Authorization: Bearer demo-key-123" \
      -H "Content-Type: application/json" \
      -X POST http://localhost:8000/api/v2/trajectory/preset/circle \
      -d '{"center": [0.5,0.5,0.3], "radius": 0.1, "duration": 4.0}'
    ```

  - curl（X-API-Key header）：
    ```bash
    curl -H "X-API-Key: demo-key-123" http://localhost:8000/api/v2/test
    ```

  - PowerShell `Invoke-RestMethod`（示例）：
    ```powershell
    Invoke-RestMethod -Uri "http://localhost:8000/api/v2/test" -Headers @{ Authorization = "Bearer demo-key-123" }
    ```

- 调整速率限制阈值（临时运行时变更）：

  - 在运行时直接修改 `app.routes._min_cmd_interval`（对当前 Python 进程生效）：

    Bash / CMD:
    ```bash
    python -c "import app.routes as r; r._min_cmd_interval = 0.2; print('min interval set to', r._min_cmd_interval)"
    ```

    PowerShell:
    ```powershell
    & .\.venv\Scripts\python.exe -c "import app.routes as r; r._min_cmd_interval = 0.2; print('min interval set to', r._min_cmd_interval)"
    ```

  - 持久化更改：编辑 `app/routes.py` 中的 `_min_cmd_interval` 行，或在部署时将该逻辑替换为从环境变量或配置文件读取（建议生产环境使用外部配置或集中速率限制服务）。

安全提醒
- 1) API key 应只用于机机/后端到后端调用；避免在不受信任的前端公开。密钥泄露会降低系统安全性。
- 2) 本项目内置的是轻量级、进程内的速率限制，适合开发和单实例部署；多实例/集群场景请替换为共享速率限制（Redis、NGINX、API Gateway）。
- 3) 紧急停止接口为安全关键路径，保持匿名访问以便现场人员快速切断指令。对生产环境，务必配备独立的物理急停电路（硬件 E-Stop），并在 `robot_config.enable_hardware_estop()` 中配置硬件后端进行联动。

## 1. 平移控制接口
### 请求地址
POST /api/v1/translate

### 请求参数
| 参数名   | 类型   | 必选 | 说明                  |
|----------|--------|------|-----------------------|
| x_offset | float  | 是   | X轴平移距离（单位：米）|
| y_offset | float  | 是   | Y轴平移距离（单位：米）|
| z_offset | float  | 是   | Z轴平移距离（单位：米）|
| duration | float  | 否   | 平移耗时（默认1秒）   |

### 响应示例
```json
{
  "code": 200,
  "msg": "平移指令执行成功",
  "data": {
    "current_pos": [2.0, 1.0, 0.0],  // 执行后的位置
    "status": "running"              // 运镜状态
  }
}
```

## 2. 旋转控制接口
### 请求地址
POST /api/v1/rotate

### 请求参数
| 参数名    | 类型   | 必选 | 说明                  |
|-----------|--------|------|-----------------------|
| angle_deg | float  | 是   | 旋转角度（单位：度）  |
| duration  | float  | 否   | 旋转耗时（默认1秒）   |

### 响应示例
```json
{
  "code": 200,
  "msg": "旋转指令执行成功",
  "data": {
    "current_angle": 90.0,  // 执行后的角度
    "status": "running"     // 运镜状态
  }
}
```

## 3. 状态查询接口
### 请求地址
GET /api/v1/status

### 请求参数
无

### 响应示例
```json
{
  "code": 200,
  "msg": "状态查询成功",
  "data": {
    "current_pos": [2.0, 1.0, 0.0],  // 当前位置
    "current_angle": 90.0,           // 当前角度
    "status": "idle",                // 状态（idle/running/error）
    "error_code": 0                  // 错误码（0表示无错误）
  }
}