import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "examples/model-review"
spec = importlib.util.spec_from_file_location("bedrock_claims", REVIEW / "bedrock_claims.py")
bedrock_claims = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bedrock_claims)

from robot_reel.claim_review import review_claims  # noqa: E402


class FakeBedrock:
    def __init__(self, text):
        self.text, self.requests = text, []

    def converse(self, **request):
        self.requests.append(request)
        return {"output": {"message": {"content": [{"text": self.text}]}}, "usage": {"inputTokens": 10, "outputTokens": 5},
                "stopReason": "end_turn", "ResponseMetadata": {"RequestId": "req-1"}}


class BedrockClaimsTests(unittest.TestCase):
    def setUp(self):
        self.protocol = json.loads((REVIEW / "protocol.json").read_text())
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        self.answer = json.dumps({"outcome": "unknown", "action_count": None, "cited_frames": [0, 160], "explanation": "x"})

    def test_request_uses_the_frozen_protocol_and_records_what_was_sent(self):
        fake = FakeBedrock("```json\n" + self.answer + "\n```")
        receipt, claims = bedrock_claims.run(fake, self.protocol, "episode-b-images-only", "m", "r", self.out, clock=iter([1.0, 3.5]).__next__)
        req = fake.requests[0]
        case = next(c for c in self.protocol["cases"] if c["id"] == "episode-b-images-only")
        self.assertEqual(req["system"][0]["text"], self.protocol["policy"])
        self.assertEqual(req["messages"][0]["content"][1]["text"], case["prompt"])
        self.assertEqual(req["inferenceConfig"], {"maxTokens": 512})
        self.assertTrue(any("temperature not sent" in d for d in receipt["deviations"]))
        self.assertEqual(receipt["image"]["sha256"], hashlib.sha256((REVIEW / "episode-b.png").read_bytes()).hexdigest())
        self.assertEqual(receipt["latency_s"], 2.5)
        self.assertEqual(claims["outcome"], "unknown")

    def test_send_sampling_adds_only_temperature(self):
        fake = FakeBedrock(self.answer)
        bedrock_claims.run(fake, self.protocol, "episode-a-with-record", "m", "r", self.out, send_sampling=True)
        self.assertEqual(fake.requests[0]["inferenceConfig"], {"maxTokens": 512, "temperature": 0.6})

    def test_recorded_answers_are_never_replaced(self):
        bedrock_claims.run(FakeBedrock(self.answer), self.protocol, "episode-b-images-only", "m", "r", self.out)
        with self.assertRaises(FileExistsError):
            bedrock_claims.run(FakeBedrock(self.answer), self.protocol, "episode-b-images-only", "m", "r", self.out)

    def test_an_answer_that_is_not_one_object_is_kept_not_repaired(self):
        receipt, claims = bedrock_claims.run(FakeBedrock("Sure! " + self.answer), self.protocol, "episode-c-images-only", "m", "r", self.out)
        self.assertIsNone(claims)
        self.assertFalse(receipt["parsed"])
        self.assertTrue((self.out / "episode-c-images-only.receipt.json").exists())
        self.assertFalse((self.out / "episode-c-images-only.claims.json").exists())

    def test_committed_bedrock_receipts_match_their_claims_and_reviews(self):
        recorded = REVIEW / "bedrock"
        receipts = sorted(recorded.glob("*.receipt.json"))
        self.assertEqual(len(receipts), 2)
        for path in receipts:
            receipt = json.loads(path.read_text())
            case = receipt["case"]
            claims = json.loads((recorded / f"{case}.claims.json").read_text())
            self.assertEqual(bedrock_claims.parse_claims(receipt["raw_text"]), claims, "claims must be the unedited answer")
            self.assertEqual(receipt["image"]["sha256"], hashlib.sha256((REVIEW / receipt["image"]["file"]).read_bytes()).hexdigest())
            episode = next(e for e in json.loads((REVIEW / "sources.json").read_text()) if case.startswith(e["id"] + "-"))
            trace_bytes = (ROOT / episode["source_directory"] / "trace.json").read_bytes()
            self.assertEqual(hashlib.sha256(trace_bytes).hexdigest(), episode["files"]["trace.json"])
            report = json.loads((recorded / f"{case}.review.json").read_text())
            self.assertEqual(review_claims(json.loads(trace_bytes), claims)["checks"], report["checks"])
            self.assertEqual(report["explanation_status"], "not_assessed")


if __name__ == "__main__":
    unittest.main()
