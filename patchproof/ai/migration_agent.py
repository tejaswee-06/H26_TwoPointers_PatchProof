
"""CLI entry point for PatchProof migration intelligence."""
import json
import sys
from pathlib import Path

from patchproof.ai.ollama_adapter import generate_migration_advice


def main():
    path = Path(
        sys.argv[1] if len(sys.argv) > 1 else "patchproof-report.json"
    )

    if not path.exists():
        raise SystemExit(f"Finding report not found: {path}")

    report = json.loads(path.read_text(encoding="utf-8"))
    findings = report if isinstance(report, list) else report.get("findings")

    if not isinstance(findings, list) or not findings:
        raise SystemExit(
            "No findings found. Inspect the report's JSON structure."
        )

    advice = generate_migration_advice(findings)
    output = Path("patchproof-ai-advice.json")
    output.write_text(
        json.dumps(advice, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Saved advice to {output}")


if __name__ == "__main__":
    main()
