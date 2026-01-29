项目根目录/
│
├── app/                           # Web应用模块
│   ├── __pycache__/              # Python字节码缓存
│   │   └── __init__.py
│   └── routes.py                 # 路由定义文件
│
├── venv/                         # Python虚拟环境
│   ├── bin/                     # 可执行文件
│   ├── include/                 # 包含文件
│   ├── lib/                     # 库文件
│   ├── lib64/                   # 64位库文件
│   └── pyvenv.cfg               # 虚拟环境配置
│
├── __pycache__/                  # 主模块字节码缓存
│   ├── dynamics_identification.cpython-310.pyc
│   ├── motion_control.cpython-310.pyc
│   ├── robot_config.cpython-310.pyc
│   ├── safety_monitor.cpython-310.pyc
│   ├── system_integration.cpython-310.pyc
│   └── test_units.cpython-310.pyc
│
├── _pycache__copy/               # 备份的字节码缓存
│   ├── motion_control.cpython-310.pyc
│   └── test_units.cpython-310.pyc
│
├── API接口设计文档V1.0.md        # API设计文档
├── dynamics_identification.py    # 动力学识别模块
├── main.py                       # 主程序入口
├── motion_control.py             # 运动控制模块
├── PROJECT_STRUCTURE.md          # 项目结构文档（本文件）
├── requirements.txt              # Python依赖列表
├── robot_config.py               # 机器人配置模块
├── safety_monitor.py             # 安全监控模块
├── system_integration.py         # 系统集成模块
├── test_advanced_features.py     # 高级功能测试
├── test_linkage.py               # 联动测试
└── test_units.py                 # 单元测试
```

## 模块说明

### 核心功能模块
- **dynamics_identification.py**: 机器人动力学参数识别
- **motion_control.py**: 运动控制算法实现
- **robot_config.py**: 机器人配置管理
- **safety_monitor.py**: 安全监控和异常处理
- **system_integration.py**: 系统集成和协调控制

### 测试模块
- **test_units.py**: 基础单元测试
- **test_linkage.py**: 多轴联动测试
- **test_advanced_features.py**: 高级功能测试

### Web应用模块
- **app/routes.py**: Web API路由定义

### 开发环境
- **venv/**: Python虚拟环境，隔离项目依赖
- **requirements.txt**: 项目依赖包列表

### 文档
- **API接口设计文档V1.0.md**: API接口详细设计说明
- **PROJECT_STRUCTURE.md**: 项目结构说明文档
