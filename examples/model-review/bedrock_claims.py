"""Run the frozen model-review protocol against a model on Amazon Bedrock (Converse API) and keep every answer.

Usage:
  python examples/model-review/bedrock_claims.py CASE_ID --model MODEL_OR_PROFILE --region REGION --output DIR

CASE_ID is one of protocol.json's cases (e.g. episode-b-images-only). Writes, without overwriting:
  DIR/CASE_ID.receipt.json  model id, Region, request id, exact system/user text, image SHA-256, inference
                            settings actually sent, protocol deviations, raw text, token usage, latency
  DIR/CASE_ID.claims.json   the JSON object parsed from the answer, unchanged (only a ``` fence is stripped)
Then check the facts offline:  robot-reel review-claims media/<episode>/trace.json DIR/CASE_ID.claims.json

Billable: one Converse call per run, about 1.7k input and 0.3k output tokens with the bundled contact sheets.
The protocol's sampling settings are sent only if --send-sampling is given; some models reject `temperature`,
and the receipt records exactly what was sent. An answer that is not one JSON object is kept in the receipt and
no claims file is written (exit 1) — the answer is never repaired.
"""
import argparse
import datetime
import hashlib
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def build_request(protocol, case_id, model, send_sampling=False):
    case = next((c for c in protocol["cases"] if c["id"] == case_id), None)
    if case is None:
        raise ValueError(f"unknown case {case_id}")
    if len(case["images"]) != 1:
        raise ValueError("expected one contact sheet per case")
    image = (HERE / case["images"][0]).read_bytes()
    config = {"maxTokens": protocol["generation"]["max_new_tokens"]}
    deviations = ["seed, top_p, top_k and enable_thinking are not Converse inferenceConfig fields and were not sent"]
    if send_sampling:
        config["temperature"] = protocol["generation"]["temperature"]
    else:
        deviations.append("temperature not sent (use --send-sampling for models that accept it)")
    request = {
        "modelId": model,
        "system": [{"text": protocol["policy"]}],
        "messages": [{"role": "user", "content": [{"image": {"format": "png", "source": {"bytes": image}}}, {"text": case["prompt"]}]}],
        "inferenceConfig": config,
    }
    return case, image, request, deviations


def parse_claims(text):
    """Return the single JSON object the protocol asks for, or None. Only a surrounding ``` fence is removed."""
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else ""
        s = s.rsplit("```", 1)[0]
    try:
        value = json.loads(s)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def run(client, protocol, case_id, model, region, output, send_sampling=False, clock=time.time):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    receipt_path, claims_path = output / f"{case_id}.receipt.json", output / f"{case_id}.claims.json"
    for p in (receipt_path, claims_path):
        if p.exists():
            raise FileExistsError(f"{p} exists; recorded answers are never replaced")
    case, image, request, deviations = build_request(protocol, case_id, model, send_sampling)
    started = clock()
    response = client.converse(**request)
    latency = clock() - started
    text = "".join(block.get("text", "") for block in response["output"]["message"]["content"])
    claims = parse_claims(text)
    receipt = {
        "schema": "robot-reel-bedrock-review-1",
        "at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "case": case_id, "model_id": model, "region": region, "api": "bedrock-runtime Converse",
        "request_id": response.get("ResponseMetadata", {}).get("RequestId"),
        "protocol_sha256": hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest(),
        "system": protocol["policy"], "prompt": case["prompt"],
        "image": {"file": case["images"][0], "sha256": hashlib.sha256(image).hexdigest()},
        "inference_config": request["inferenceConfig"], "deviations": deviations,
        "raw_text": text, "parsed": claims is not None,
        "usage": response.get("usage"), "stop_reason": response.get("stopReason"), "latency_s": round(latency, 2),
    }
    receipt_path.write_text(json.dumps(receipt, indent=1, ensure_ascii=False) + "\n")
    if claims is not None:
        claims_path.write_text(json.dumps(claims, indent=1, ensure_ascii=False) + "\n")
    return receipt, claims


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("case")
    ap.add_argument("--model", required=True, help="Bedrock model or inference profile id (billable)")
    ap.add_argument("--region", required=True)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--send-sampling", action="store_true", help="also send the protocol temperature")
    args = ap.parse_args(argv)
    import boto3  # only the live path needs it
    protocol = json.loads((HERE / "protocol.json").read_text())
    client = boto3.client("bedrock-runtime", region_name=args.region)
    receipt, claims = run(client, protocol, args.case, args.model, args.region, args.output, args.send_sampling)
    print(f"{args.case}: {receipt['usage']} latency {receipt['latency_s']} s, request {receipt['request_id']}")
    if claims is None:
        print("answer was not one JSON object; kept in the receipt, no claims file written", file=sys.stderr)
        return 1
    print(json.dumps({k: claims.get(k) for k in ("outcome", "action_count", "cited_frames")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
