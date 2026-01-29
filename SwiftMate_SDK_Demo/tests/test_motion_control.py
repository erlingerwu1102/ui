import unittest
from unittest import mock

import time

class MotionControlTest(unittest.TestCase):
    def test_simulation_unavailable_raises_importerror(self):
        # Patch ensure_simulation to simulate pybullet missing
        import motion_control as mc

        with mock.patch.object(mc, 'ensure_simulation', return_value=False):
            with self.assertRaises(ImportError):
                mc.translate_object(None, 0.1, 0, 0, duration=0.001)

    def test_simulation_translate_rotate_runs_when_available(self):
        import motion_control as mc

        # Ensure the simulation is initialized (lazy init) if available
        ok = mc.ensure_simulation()
        if not ok:
            self.skipTest('pybullet not available in this environment')

        # Run quick translate and rotate with tiny durations to keep test fast
        mc.translate_object(None, 0.01, 0, 0, duration=0.01)
        mc.rotate_object(None, 5, duration=0.01)

        status = mc.get_current_status()
        self.assertIn('status', status)
        self.assertIn('current_pos', status)
        self.assertIsInstance(status['current_pos'], list)

        # Try reset
        self.assertTrue(mc.reset_error())


if __name__ == '__main__':
    unittest.main()
