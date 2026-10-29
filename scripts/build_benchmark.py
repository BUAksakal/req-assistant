import json
from pathlib import Path

from build_examples import build_pdf, load_spec

BENCH = Path(__file__).resolve().parent.parent / "bench"
# dev: used to tune prompts. test: held out, only reported.
SPECS = {"dev": "acc", "test": "epb"}


if __name__ == "__main__":
    for name in SPECS.values():
        spec = load_spec(BENCH / f"{name}_benchmark.yaml")
        build_pdf(spec, BENCH / f"{name}_benchmark.pdf")
        key = spec["answer_key"]
        key["requirements"] = [
            req["id"] for sec in spec["sections"] for req in sec.get("requirements", [])
        ]
        answer_key = BENCH / f"{name}_answer_key.json"
        answer_key.write_text(json.dumps(key, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {name}_benchmark.pdf and {answer_key.name}")
