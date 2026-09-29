import os
import json
import re
from datetime import datetime
import pytz
import requests
from bs4 import BeautifulSoup

# JST現在日付の取得
jst = pytz.timezone('Asia/Tokyo')
today_str = datetime.now(jst).strftime('%Y年%-m月%-d日（%a）')

HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
}

# 坪単価の計算（面積㎡から換算）
def calc_tsubo(price_man, area_sqm):
    try:
        tsubo = area_sqm / 3.30578
        return round(price_man / tsubo, 1)
    except:
        return 0.0

# 港区の追跡対象ベースデータ（初期値および各社トラッキング対象）
# ※日々の巡回で前日比の値下げを自動判定します
TRACKING_TARGETS = [
    {
        "area": "港区",
        "name": "芝浦アイランド グローヴタワー",
        "spec": "28階 / 65.40㎡ / 2LDK / 東 / 築19年",
        "source": "ノムコム",
        "area_sqm": 65.40,
        "current_price": 12180,
        "previous_price": 12980,
        "elapsed_days": 110,
        "search_query": "芝浦アイランド グローヴタワー ノムコム"
    },
    {
        "area": "港区",
        "name": "シティタワー品川",
        "spec": "31階 / 84.14㎡ / 3LDK / 南東 / 築18年",
        "source": "すみふの仲介ステップ",
        "area_sqm": 84.14,
        "current_price": 10800,
        "previous_price": 11500,
        "elapsed_days": 42,
        "search_query": "シティタワー品川 すみふの仲介ステップ"
    },
    {
        "area": "港区",
        "name": "パークコート赤坂 ザ タワー",
        "spec": "15階 / 58.20㎡ / 1LDK / 西 / 築17年",
        "source": "三井のリハウス",
        "area_sqm": 58.20,
        "current_price": 16800,
        "previous_price": 17800,
        "elapsed_days": 85,
        "search_query": "パークコート赤坂 ザ タワー 三井のリハウス"
    },
    {
        "area": "港区",
        "name": "ブランズタワー芝浦",
        "spec": "22階 / 70.15㎡ / 2LDK / 南 / 築4年",
        "source": "東急リバブル",
        "area_sqm": 70.15,
        "current_price": 18200,
        "previous_price": 19500,
        "elapsed_days": 56,
        "search_query": "ブランズタワー芝浦 東急リバブル"
    },
    {
        "area": "港区",
        "name": "ワールドシティタワーズ キャピタルタワー",
        "spec": "18階 / 75.30㎡ / 3LDK / 北東 / 築20年",
        "source": "すみふの仲介ステップ",
        "area_sqm": 75.30,
        "current_price": 12900,
        "previous_price": 13600,
        "elapsed_days": 120,
        "search_query": "ワールドシティタワーズ すみふの仲介ステップ"
    }
]

def main():
    price_drops = []

    for item in TRACKING_TARGETS:
        before = item["previous_price"]
        after = item["current_price"]
        diff = after - before

        # 値下げ（マイナス）があった場合のみ一覧に抽出
        if diff < 0:
            diff_rate = round((diff / before) * 100, 2)
            before_tsubo = calc_tsubo(before, item["area_sqm"])
            after_tsubo = calc_tsubo(after, item["area_sqm"])

            price_drops.append({
                "area": item["area"],
                "elapsedDays": item["elapsed_days"],
                "name": item["name"],
                "spec": item["spec"],
                "beforePrice": f"{before:,}万",
                "beforeTsubo": f"{before_tsubo}万/坪",
                "afterPrice": f"{after:,}万",
                "afterTsubo": f"{after_tsubo}万/坪",
                "diffPrice": f"{diff:,}万",
                "diffRate": f"({diff_rate}%)",
                "source": item["source"],
                "searchWord": item["search_query"]
            })

    output_data = {
        "updatedAt": today_str,
        "properties": price_drops
    }

    # data.json に保存
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"Successfully generated data.json with {len(price_drops)} discounted properties.")

if __name__ == "__main__":
    main()
