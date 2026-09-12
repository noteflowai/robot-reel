import re
from pathlib import Path
import unittest

from robot_reel.stress_mcap import records
from robot_reel.stress_site import load_collection

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT/"docs/telemetry.md"
# The subset of FoxQL the guide uses: a topic, then dotted fields with an
# optional [index] or [:] slice.
EXPRESSION = re.compile(r"^(/[\w-]+/\w+)((?:\.\w+(?:\[(?:\d+|:)\])?)+)$", re.M)


def resolve(message, path):
    """Walk a documented field path from the message root."""
    value = message
    for step in path.lstrip(".").split("."):
        name, _, index = step.partition("[")
        value = value[name]
        if index == ":]":
            if not isinstance(value, list):
                raise TypeError(f"{step} is not a list")
        elif index:
            value = value[int(index.rstrip("]"))]
    return value


class TelemetryGuideTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, _, traces = load_collection(ROOT/"docs/stress")
        cls.rows = list(records(traces))
        cls.samples = {}
        for topic, _, _, row in cls.rows:
            # Keep a sample with an applied control: the terminal observation has none.
            if topic not in cls.samples or cls.samples[topic]["sample"].get("action") is None:
                cls.samples[topic] = row
        cls.text = GUIDE.read_text()
        cls.expressions = EXPRESSION.findall(cls.text)

    def test_the_guide_documents_expressions(self):
        self.assertGreaterEqual(len(self.expressions), 8)

    def test_every_documented_expression_resolves_against_the_telemetry(self):
        for topic, path in self.expressions:
            with self.subTest(expression=topic+path):
                self.assertIn(topic, self.samples, f"{topic} is not a recorded topic")
                value = resolve(self.samples[topic], path)
                if isinstance(value, list):
                    self.assertTrue(value and all(isinstance(v, (int, float)) for v in value))
                else:
                    self.assertIsInstance(value, (int, float, bool))

    def test_documented_counts_match_the_export(self):
        # The sentence wraps in the source, so compare against flattened text.
        stated = re.search(r"(\d+) messages on (\d+) topics: (\d+) observations and "
                           r"(\d+) inference calls across (\d+) trials",
                           re.sub(r"\s+", " ", self.text))
        self.assertIsNotNone(stated, "the guide must state its message counts")
        topics = {topic for topic, _, _, _ in self.rows}
        self.assertEqual([int(number) for number in stated.groups()], [
            len(self.rows), len(topics),
            sum(1 for topic, _, _, _ in self.rows if topic.endswith("/observation")),
            sum(1 for topic, _, _, _ in self.rows if topic.endswith("/inference")),
            len(topics)//2,
        ])

    def test_documented_action_channels_match_the_traces(self):
        _, _, traces = load_collection(ROOT/"docs/stress")
        channels = traces[0]["channels"]
        self.assertEqual(len(channels), 7)
        for name in channels:
            self.assertIn(f"`{name}`", self.text, name)
        # The gripper index the guide points at has to be the last channel.
        self.assertEqual(channels.index("gripper"), 6)
