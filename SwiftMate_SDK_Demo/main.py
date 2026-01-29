import os
from app import create_app
from safety_monitor import safety_monitor

app = create_app()

# 启动安全监控
safety_monitor.start_monitoring()
import logging
logging.getLogger(__name__).info("安全监控系统已启动")

if __name__ == "__main__":
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(
        debug=debug_mode,
        host=os.getenv('FLASK_HOST', '0.0.0.0'),
        port=int(os.getenv('FLASK_PORT', 8000)),
        threaded=True
    )