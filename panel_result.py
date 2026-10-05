"""Panel results are uploaded as authenticated Actions artifacts, never committed."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

def panel_only():
    return os.getenv("PANEL_ONLY", "").lower() == "true"

def write_result(kind, **data):
    payload = {"schema": 1, "kind": kind, "checkedAt": datetime.now(timezone.utc).isoformat(),
               "runId": os.getenv("GITHUB_RUN_ID", ""), **data}
    Path("panel-result.json").write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")

def person_summary(person):
    return {"name": (person["Ad"] + " " + person["Soyad"]).strip(), "department": person["Birim"], "role": person["Görev"]}
