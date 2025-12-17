import json
from pathlib import Path
from typing import Any, Dict, Optional

# Path to shared JSON (adjust if layout differs)
BASE_DIR = Path(__file__).resolve().parents[1]
BENCHMARKS_PATH = BASE_DIR / "shared" / "iris2025_benchmarks.json"

with BENCHMARKS_PATH.open("r", encoding="utf-8") as f:
    IRIS_2025 = json.load(f)

def get_lef_benchmark(industry: Optional[str] = None,
                      revenue: Optional[str] = None) -> Dict[str, Any]:
    data = IRIS_2025
    result: Dict[str, Any] = {
        "industry": None,
        "revenue": None,
        "overall_baseline": data["lef_overall_baseline"],
    }

    if industry:
        result["industry"] = data["lef_by_industry"].get(
            industry,
            {
                "probability": None,
                "confidence": "none",
                "description": f"No data available for {industry}",
                "source": data["metadata"]["source"],
            },
        )

    if revenue:
        if revenue in data["lef_by_revenue"]:
            result["revenue"] = data["lef_by_revenue"][revenue]

    return result

def get_lm_benchmark(industry: Optional[str] = None,
                     revenue: Optional[str] = None) -> Dict[str, Any]:
    data = IRIS_2025
    result: Dict[str, Any] = {
        "industry": None,
        "revenue": None,
        "overall_baseline": data["lm_overall_baseline"],
    }

    if industry:
        result["industry"] = data["lm_by_industry"].get(industry)

    if revenue:
        result["revenue"] = data["lm_by_revenue"].get(revenue)

    return result