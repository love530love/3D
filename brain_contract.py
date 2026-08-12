"""Validate the evidence-brain contract before a decision is published."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED = {"brain_version", "verdict", "recommendation", "quality_gate", "evolution_policy", "disclaimer"}


def main() -> int:
    p = argparse.ArgumentParser(description="验证综合证据大脑输出契约")
    base = Path(__file__).parent
    p.add_argument("--input", type=Path, default=base / "reports" / "brain-decision-latest.json")
    args = p.parse_args()
    try:
        document = json.loads(args.input.read_text(encoding="utf-8"))
        errors = []
        missing = sorted(REQUIRED - set(document))
        policy = document.get("evolution_policy", {})
        if missing:
            errors.append(f"missing fields: {missing}")
        if policy.get("auto_modify_code") is not False or policy.get("auto_delete_data") is not False:
            errors.append("automatic code/data mutation must be disabled")
        if policy.get("requires_expert_audit_for_model_change") is not True:
            errors.append("expert audit requirement missing")
        if document.get("quality_gate", {}).get("status") != "PASS":
            errors.append("quality gate is not PASS")
        disclaimer = document.get("disclaimer", "")
        if "预测" not in disclaimer or ("不" not in disclaimer and "not" not in disclaimer.lower()):
            errors.append("disclaimer missing non-prediction boundary")
        status = "PASS" if not errors else "FAIL"
        print(f"Brain contract: {status}")
        for error in errors:
            print(f"- {error}")
        return 0 if status == "PASS" else 1
    except (OSError, ValueError, TypeError) as exc:
        print(f"Brain contract: FAIL ({exc})")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
