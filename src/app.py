"""
LinkedIn Post Ghostwriter - Flask Web Service.

Purpose:
    Exposes an HTTP POST/GET endpoint for Cloud Scheduler weekly automated triggers.
    
Endpoints:
    - POST /: Triggers the LinkedIn ghostwriter pipeline. Accepts query parameter `?days=N`
              or JSON payload `{"days": N, "dry_run": bool}`.
    - GET /: Health check / manual invocation endpoint supporting `?days=N` & `?dry_run=bool`.
"""

from __future__ import annotations

import os
from typing import Any
from flask import Flask, Response, jsonify, request

from src.main import run_pipeline

app: Flask = Flask(__name__)


@app.route("/", methods=["POST", "GET"])
def trigger_ghostwriter() -> tuple[Response, int]:
    """HTTP trigger route for scheduled weekly execution."""
    try:
        days: int = request.args.get("days", default=7, type=int)
        dry_run: bool = request.args.get(
            "dry_run", default=False, type=lambda v: str(v).lower() in ("true", "1")
        )

        if request.is_json:
            data = request.get_json(silent=True)
            if data:
                if "days" in data:
                    days = int(data["days"])
                if "dry_run" in data:
                    dry_run = bool(data["dry_run"])

        print(f"[WebService] Trigger received: lookback={days}d, dry_run={dry_run}")
        result: dict[str, Any] = run_pipeline(dry_run=dry_run, days=days)

        if result.get("success"):
            return (
                jsonify(
                    {
                        "status": "success",
                        "message": "LinkedIn Post Ghostwriter executed successfully",
                        "topic": result.get("topic"),
                        "stats": result.get("stats", {}),
                        "elapsed_seconds": result.get("elapsed_seconds"),
                    }
                ),
                200,
            )
        else:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": result.get("error", "Execution failed"),
                        "stats": result.get("stats", {}),
                        "elapsed_seconds": result.get("elapsed_seconds"),
                    }
                ),
                500,
            )

    except Exception as exc:
        print(f"[WebService] Unhandled server error: {exc}")
        return jsonify({"status": "error", "message": str(exc)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
