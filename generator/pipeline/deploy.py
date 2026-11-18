"""Deploy the rebuilt worker.js to Cloudflare (Workers Scripts API).

The pla365 Worker is a static bundle with no bindings; the upload is
a multipart PUT with the script as the main module — the same route
the old generator's API deployments used (compatibility_date
2025-01-01, as on the live script).
"""
from __future__ import annotations

import json

import requests

API = "https://api.cloudflare.com/client/v4"


def deploy(worker_js, account_id, token, script="pla365", timeout=180):
    metadata = {"main_module": "worker.js", "compatibility_date": "2025-01-01"}
    files = {
        "metadata": ("metadata.json", json.dumps(metadata), "application/json"),
        "worker.js": ("worker.js", worker_js.encode("utf-8"),
                      "application/javascript+module"),
    }
    r = requests.put(f"{API}/accounts/{account_id}/workers/scripts/{script}",
                     headers={"Authorization": f"Bearer {token}"},
                     files=files, timeout=timeout)
    data = r.json()
    if not data.get("success"):
        raise RuntimeError(f"deploy failed: {data.get('errors')}")
    return data["result"]
