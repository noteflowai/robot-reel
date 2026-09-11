import unittest

from robot_reel.capture import validate_targets


class TargetsTest(unittest.TestCase):
    def test_invalid_targets_are_rejected_before_execution(self):
        for target in ({}, {"missing": 0}, {"joint": float("nan")},
                       {"joint": float("inf")}, {"joint": True},
                       {"joint": 2}, {"joint": "0"}):
            with self.subTest(target=target), self.assertRaises(ValueError):
                validate_targets(target, ["joint"], [(-1, 1)])

    def test_limits_are_inclusive(self):
        for value in [-1, 0, 1]:
            validate_targets({"joint": value}, ["joint"], [(-1, 1)])



if __name__ == "__main__":
    unittest.main()
