# 依赖与安装说明

本项目把依赖分为三类：核心运行依赖、可选（仿真 / 深度学习）依赖，以及开发/测试依赖。默认只需要安装核心依赖；可选依赖用于运行 pybullet 仿真或 notebook 中的模型。

## 文件说明
- `requirements.txt` - 核心运行依赖（运行 API 服务时需要）。
- `requirements-optional.txt` - 可选依赖：物理仿真（`pybullet`）和深度学习库（`torch`）。仅在需要仿真或训练时安装。
- `requirements-dev.txt` - 开发与测试辅助依赖（格式化、静态检查、CI 工具等）。

## 快速安装（Windows PowerShell）

1) 创建并激活虚拟环境

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2) 安装核心依赖（运行 API 服务）

```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

3) （可选）安装仿真或深度学习依赖

```powershell
pip install -r requirements-optional.txt
```

4) （可选）安装开发/测试依赖

```powershell
pip install -r requirements-dev.txt
```

## 说明与建议
- 若只想运行 API 服务并跳过仿真，请不要安装 `requirements-optional.txt`，并确保在运行环境中通过环境变量或配置禁用仿真初始化（例如 `SIMULATE_PHYSICS=false`）。
- `pybullet` 在某些平台需要合适的二进制 wheel 或本机编译工具链；遇到问题请参考 pybullet 官方安装指南或在 CI 中使用预构建镜像。
- 为便于追踪与复现，CI 使用 `requirements.txt` 安装依赖；可在 CI 中添加 `pip install -r requirements-optional.txt` 的矩阵项以覆盖仿真测试。

如需我把项目改为在首次使用时懒加载 `pybullet`（降低启动时对可选依赖的要求），我可以接着实现并添加相应单元测试与 README 指示。
