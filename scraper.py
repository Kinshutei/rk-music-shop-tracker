import requests
import json
import os
from datetime import datetime, timezone, timedelta

BASE_URL = "https://shop.reality-studios.inc"
COLLECTION = "rkmusic-all"
DATA_DIR = os.path.join(os.path.dirname(__file__), "docs", "data")

EXCLUDED_TAGS = {
    "RK Music", "KMNLABEL", "Fused",
    "NEW", "受注生産商品", "在庫限り", "在庫限り商品", "販売終了商品", "ライブグッズ", "ぬいぐるみ", "ミニぬい",
    "Bundle", "セット", "ノベルティ",
}

JST = timezone(timedelta(hours=9))


def fetch_all_products():
    products = []
    page = 1
    while True:
        url = f"{BASE_URL}/collections/{COLLECTION}/products.json?limit=250&page={page}"
        resp = requests.get(url, headers={"User-Agent": "rk-music-shop-tracker/1.0 (personal fan tool; https://github.com/Kinshutei/rk-music-shop-tracker)"}, timeout=30)
        resp.raise_for_status()
        batch = resp.json().get("products", [])
        if not batch:
            break
        products.extend(batch)
        if len(batch) < 250:
            break
        page += 1
    return products


def extract_singers(tags):
    return [t for t in tags if t not in EXCLUDED_TAGS]


def normalize(products):
    result = []
    for p in products:
        thumbnail = p["images"][0]["src"] if p.get("images") else None
        singers = extract_singers(p.get("tags", []))
        variants = [
            {
                "title": v["title"],
                "price": int(v["price"]),
                "available": v["available"],
            }
            for v in p.get("variants", [])
        ]
        result.append({
            "id": p["id"],
            "title": p["title"],
            "handle": p["handle"],
            "singers": singers,
            "tags": p.get("tags", []),
            "thumbnail": thumbnail,
            "url": f"{BASE_URL}/products/{p['handle']}",
            "published_at": p["published_at"],
            "updated_at": p["updated_at"],
            "variants": variants,
        })
    return result


def detect_changes(prev, current):
    prev_by_id = {p["id"]: p for p in prev}
    curr_by_id = {p["id"]: p for p in current}

    new_products = [p for pid, p in curr_by_id.items() if pid not in prev_by_id]
    removed_products = [p for pid, p in prev_by_id.items() if pid not in curr_by_id]

    availability_changes = []
    for pid, curr_p in curr_by_id.items():
        if pid not in prev_by_id:
            continue
        prev_p = prev_by_id[pid]
        prev_variants = {v["title"]: v for v in prev_p["variants"]}
        for v in curr_p["variants"]:
            pv = prev_variants.get(v["title"])
            if pv and pv["available"] != v["available"]:
                availability_changes.append({
                    "product_title": curr_p["title"],
                    "singers": curr_p["singers"],
                    "variant": v["title"],
                    "before": pv["available"],
                    "after": v["available"],
                })

    return {
        "new_products": new_products,
        "removed_products": removed_products,
        "availability_changes": availability_changes,
    }


def load_json(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    latest_path = os.path.join(DATA_DIR, "products_latest.json")
    prev_path = os.path.join(DATA_DIR, "products_prev.json")
    changelog_path = os.path.join(DATA_DIR, "changelog.json")

    prev_products = load_json(latest_path)

    raw = fetch_all_products()
    current_products = normalize(raw)

    changes = detect_changes(prev_products, current_products)

    scraped_at = datetime.now(JST).isoformat()

    # 差分があった場合のみchangelogに追記
    if changes["new_products"] or changes["removed_products"] or changes["availability_changes"]:
        changelog = load_json(changelog_path)
        changelog.insert(0, {
            "date": scraped_at,
            "new_products": changes["new_products"],
            "removed_products": changes["removed_products"],
            "availability_changes": changes["availability_changes"],
        })
        # 直近90日分だけ保持
        save_json(changelog_path, changelog[:90])

    # スナップショット更新
    if prev_products:
        save_json(prev_path, prev_products)
    save_json(latest_path, current_products)

    # UIが読む統合JSONを出力
    save_json(os.path.join(DATA_DIR, "data.json"), {
        "scraped_at": scraped_at,
        "products": current_products,
        "latest_changes": changes,
    })

    print(f"[{scraped_at}] 商品数: {len(current_products)}")
    print(f"  新着: {len(changes['new_products'])} 件")
    print(f"  消えた: {len(changes['removed_products'])} 件")
    print(f"  在庫変化: {len(changes['availability_changes'])} 件")


if __name__ == "__main__":
    main()
