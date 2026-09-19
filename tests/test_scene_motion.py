import math
from pathlib import Path
import tempfile
import unittest

from robot_reel.scene_motion import (
    browser_point, camera_axes, checked_file, height_at, identity, project,
)


class SceneMotionTests(unittest.TestCase):
    def test_nonplanar_proxy_uses_its_declared_diagonal(self):
        # Lower-left cell has three zero vertices and a 4 m far corner.
        # Its anti-diagonal keeps the first triangle at zero height.
        terrain = {"resolution": 3, "bounds": [[-2, -4, 0], [2, 4, 4]],
                   "heights_m": [0, 0, 0, 0, 4, 0, 0, 0, 0]}
        self.assertAlmostEqual(height_at(terrain, -1.5, -3), 0)
        self.assertAlmostEqual(height_at(terrain, -.5, -1), 2)
        self.assertAlmostEqual(height_at(terrain, 0, 0), 4)
        with self.assertRaises(ValueError):
            height_at(terrain, 2.001, 0)

    def test_camera_projects_world_axes_to_top_left_image(self):
        axes = camera_axes([0, -5, 0], [0, 0, 0])
        camera = {"position_m": [0, -5, 0], "axes_world": axes,
                  "focal_px": [500, 500], "principal_px": [500, 300]}
        self.assertEqual(project(camera, [0, 0, 0]), [500, 300, 5])
        self.assertEqual(project(camera, [1, 0, 2]), [600, 100, 5])
        self.assertIsNone(project(camera, [0, -6, 0]))
        with self.assertRaises(ValueError):
            camera_axes([0, 0, 0], [0, 0, 0])

    def test_browser_conversion_preserves_metre_distance(self):
        a, b = [1, 2, 3], [-4, 5, 2]
        self.assertEqual(browser_point(a), [1, 3, -2])
        self.assertAlmostEqual(math.dist(a, b), math.dist(browser_point(a), browser_point(b)))
        with self.assertRaises(ValueError):
            browser_point([float("nan"), 0, 0])

    def test_reviewed_sources_reject_changed_bytes_and_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "model.xml"
            source.write_text("<mujoco/>")
            expected = identity(source)
            self.assertEqual(checked_file(root, "model.xml", expected), source)
            source.write_text("<mujoco model='changed'/>")
            with self.assertRaises(ValueError):
                checked_file(root, "model.xml", expected)
            with self.assertRaises(ValueError):
                checked_file(root, "../model.xml", expected)
            link = root / "linked.xml"
            link.symlink_to(source)
            with self.assertRaises(ValueError):
                checked_file(root, "linked.xml", identity(source))


if __name__ == "__main__":
    unittest.main()
