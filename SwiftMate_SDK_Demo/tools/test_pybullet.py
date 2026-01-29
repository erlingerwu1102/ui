import pybullet as p
import traceback
print('pybullet version:', getattr(p, '__version__', None))
try:
    cid = p.connect(p.DIRECT)
    print('connected cid=', cid)
    p.disconnect()
except Exception as e:
    print('connect failed:', e)
    traceback.print_exc()
