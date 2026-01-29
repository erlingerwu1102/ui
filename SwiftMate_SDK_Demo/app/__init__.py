from flask import Flask
from flask_cors import CORS

def create_app():
    # 初始化Flask应用
    app = Flask(__name__)

    # 启用跨域，限制在 /api/* 路径，默认允许所有来源与常用方法/头
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    
    # 注册接口路由
    from app.routes import bp
    app.register_blueprint(bp)
    # 注册高级路由（若存在）
    try:
        from app.routes import bp_v2
        app.register_blueprint(bp_v2)
    except Exception:
        import logging
        logging.getLogger(__name__).warning("未找到 bp_2，跳过 2 路由注册")

    # 注册统一错误处理
    try:
        from app.error_handlers import register_error_handlers

        register_error_handlers(app)
    except Exception:
        # 如果注册失败，记录但不阻塞应用启动
        import logging

        logging.getLogger(__name__).exception("Failed to register error handlers")
    
    # 添加一个简单的测试路由
    @app.route('/')
    def hello():
        return "Flask服务器运行正常！"
    
    return app