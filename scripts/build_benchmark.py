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
        reqs = [req for sec in spec["sections"] for req in sec.get("requirements", [])]
        key["requirements"] = [req["id"] for req in reqs]
        # Texts let retrieval be measured without PDF extraction or an LLM.
        key["texts"] = {req["id"]: req["text"] for req in reqs}
        answer_key = BENCH / f"{name}_answer_key.json"
        answer_key.write_text(json.dumps(key, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {name}_benchmark.pdf and {answer_key.name}")
