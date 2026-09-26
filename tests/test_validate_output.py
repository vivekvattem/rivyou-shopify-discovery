import json
import importlib.util
from pathlib import Path

import pandas as pd

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_output.py"
SPEC = importlib.util.spec_from_file_location("validate_output", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_logo_rejection_checks_asset_path_not_merchant_domain(tmp_path):
    path = tmp_path / "stores.csv"
    pd.DataFrame([{
        "domain_url": "https://tavisa.in",
        "contacts": json.dumps({"emails": ["care@tavisa.in"], "phones": []}),
        "socials": json.dumps({}),
        "category": "Fashion",
        "tagline_or_description": "Indian fashion store",
        "logo_url": "https://tavisa.in/cdn/shop/files/logo_black.png",
        "state": "Delhi",
        "shopify_score": "12",
        "india_score": "8",
    }]).to_csv(path, index=False)

    assert MODULE.validate(path) == 0
