import json
from pathlib import Path

from build_examples import build_pdf, load_spec

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "bench" / "acc_benchmark.yaml"
OUTPUT = ROOT / "bench" / "acc_benchmark.pdf"
ANSWER_KEY = ROOT / "bench" / "acc_answer_key.json"


if __name__ == "__main__":
    spec = load_spec(SOURCE)
    build_pdf(spec, OUTPUT)
    key = spec["answer_key"]
    key["requirements"] = [
        req["id"] for sec in spec["sections"] for req in sec.get("requirements", [])
    ]
    ANSWER_KEY.write_text(json.dumps(key, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT} and {ANSWER_KEY}")
