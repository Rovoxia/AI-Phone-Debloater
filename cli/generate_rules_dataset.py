#!/usr/bin/env python3
"""Generate web/src/data/rules-dataset.json from cli/rules/*.json rule files.

Stdlib-only. Reads every rule database, merges them into a single rules list,
derives per-rule fields (brand, oemId, oemGroup, severity), computes stats, and
writes a JSON dataset matching the schema consumed by web/src/pages/oems.astro.
"""

import json
import logging
import os
from collections import Counter
from glob import glob

RULES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules")
DATASET_PATH = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web", "src", "data", "rules-dataset.json")
)

# manufacturer (from rule file header) -> (brand, oemId)
OEM_MAP = {
    "BBK (Oppo, Vivo, Realme)": ("BBK", "bbk"),
    "Android (all OEMs)": ("Core System", "critical"),
    "Google": ("Google", "pixel"),
    "huawei": ("Huawei", "huawei"),
    "Motorola": ("Motorola", "motorola"),
    "OnePlus": ("OnePlus", "oneplus"),
    "Samsung": ("Samsung", "samsung"),
    "Transsion (Tecno, Infinix, Itel)": ("Transsion", "transsion"),
    "Universal (All OEMs)": ("Universal", "universal"),
    "Xiaomi": ("Xiaomi", "xiaomi"),
}

SEVERITY_BY_TIER = {1: "SAFE", 2: "CAUTION", 3: "CRITICAL", 4: "CRITICAL_BRICK_RISK"}


def load_rules():
    rules = []
    for path in sorted(glob(os.path.join(RULES_DIR, "*.json"))):
        source_file = os.path.basename(path)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logging.warning("Skipping malformed rule file %s: %s", source_file, exc)
            continue
        if not isinstance(data, dict) or not isinstance(data.get("rules"), list):
            logging.warning("Skipping %s: missing 'rules' list", source_file)
            continue

        manufacturer = data.get("manufacturer", "") or ""
        brand_default, oemid_default = OEM_MAP.get(
            manufacturer, (manufacturer, manufacturer.lower())
        )

        for rule in data["rules"]:
            if not isinstance(rule, dict) or not rule.get("package"):
                continue

            tier = rule.get("tier", 4)
            if not isinstance(tier, int) or tier < 1 or tier > 4:
                tier = 4

            rules.append(
                {
                    "package": rule["package"],
                    "name": rule.get("name"),
                    "oemId": rule.get("oemId") or oemid_default,
                    "brand": rule.get("brand") or brand_default,
                    "oemGroup": rule.get("oemGroup") or manufacturer,
                    "tier": tier,
                    "category": rule.get("category", ""),
                    "description": rule.get("description", ""),
                    "safe_to_remove": bool(rule.get("safe_to_remove", False)),
                    "recommended_action": rule.get("recommended_action", ""),
                    "sourceFile": source_file,
                    "severity": rule.get("severity") or SEVERITY_BY_TIER[tier],
                }
            )

    rules.sort(key=lambda r: r["package"])
    return rules


def build_stats(rules):
    tier_counts = Counter(r["tier"] for r in rules)
    oem_breakdown = Counter(r["brand"] for r in rules)
    category_breakdown = Counter(r["category"] for r in rules)
    return {
        "totalCount": len(rules),
        "totalRules": len(rules),
        "tier1Count": tier_counts[1],
        "tier2Count": tier_counts[2],
        "tier3Count": tier_counts[3],
        "tier4CriticalCount": tier_counts[4],
        "oemBreakdown": dict(sorted(oem_breakdown.items())),
        "categoryBreakdown": dict(sorted(category_breakdown.items())),
    }


def main():
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    rules = load_rules()
    dataset = {"totalCount": len(rules), "stats": build_stats(rules), "rules": rules}
    with open(DATASET_PATH, "w", encoding="utf-8") as fh:
        json.dump(dataset, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(f"Wrote {len(rules)} rules to {DATASET_PATH}")


if __name__ == "__main__":
    main()
