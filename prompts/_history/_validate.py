"""Validate planner_v2 output JSON against Matrix schema."""
import json
import re
from pathlib import Path

p = Path(__file__).resolve().parents[2] / "prompts" / "_history" / "planner_v2_output.md"
s = p.read_text(encoding="utf-8")
# Strip outer fence + inner ```json ... ```
m = re.search(r"```json\s*```json\s*(\{.*?\})\s*```\s*```", s, re.S)
if not m:
    m = re.search(r"```json\s*(\{.*?\})\s*```", s, re.S)
assert m, "no json block found"
j = json.loads(m.group(1))

assert "question_id" in j and j["question_id"]
assert 5 <= len(j["domains"]) <= 7, f"domains={len(j['domains'])}"
assert 10 <= len(j["cells"]) <= 15, f"cells={len(j['cells'])}"
for c in j["cells"]:
    for k in ("id", "domain", "layer", "scout_task"):
        assert k in c
    assert c["domain"] in j["domains"], f"unknown domain {c['domain']}"
    st = c["scout_task"]
    assert st["cell_id"] == c["id"]
    assert st["query"]
    assert 2 <= len(st["target_sources"]) <= 5
print(
    f"OK: {len(j['domains'])} domains, {len(j['cells'])} cells, "
    f"all scout_tasks well-formed"
)
