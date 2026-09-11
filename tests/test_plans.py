import copy
import unittest
from robot_reel.plans import DEFAULT_PLAN, validate_plan


class PlanTest(unittest.TestCase):
    def test_rejects_empty_missing_and_unsupported_plans(self):
        for plan in (None, {}, {"version": 2, "shots": []}, {"version": True, "shots": []}):
            with self.subTest(plan=plan), self.assertRaises(ValueError):
                validate_plan(plan)

    def test_every_plan_ends_at_asset_home(self):
        plan = copy.deepcopy(DEFAULT_PLAN)
        plan["shots"][-1] = {"label": "Wrong home", "targets": {"Rotation": 0}}
        with self.assertRaisesRegex(ValueError, "home: true"):
            validate_plan(plan)

    def test_rejects_ambiguous_or_nonfinite_targets(self):
        for targets in ({}, {"Rotation": float("nan")}, {"Rotation": True}, {"Rotation": "0"}):
            plan = copy.deepcopy(DEFAULT_PLAN)
            plan["shots"][0]["targets"] = targets
            with self.subTest(targets=targets), self.assertRaises(ValueError):
                validate_plan(plan)

    def test_rejects_unknown_fields_instead_of_ignoring_user_intent(self):
        plan = copy.deepcopy(DEFAULT_PLAN)
        plan["shots"][0]["duration"] = 10
        with self.assertRaises(ValueError):
            validate_plan(plan)

    def test_valid_plan_is_unchanged(self):
        original = copy.deepcopy(DEFAULT_PLAN)
        self.assertEqual(validate_plan(original), DEFAULT_PLAN)
