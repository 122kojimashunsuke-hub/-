import os
import json
from datetime import datetime
import pytz

jst = pytz.timezone('Asia/Tokyo')
today_str = datetime.now(jst).strftime('%Y年%-m月%-d日（%a）')

# オーナーチェンジ・賃貸中・投資用物件の除外ブラックリスト
INVESTMENT_EXCLUDE_WORDS = [
    "オーナーチェンジ", "賃貸中", "利回り", "表面利回り", 
    "想定利回り", "想定年収", "現況：賃貸", "投資用", "借家"
]

def calc_tsubo(price_man, area_sqm):
    try:
        tsubo = area_sqm / 3.30578
        return round(price_man / tsubo, 1)
    except:
        return 0.0

# 追跡データベース（区別・実需向けタワー＆レジデンス）
MASTER_DATA = [
    # --- 港区 ---
    {
        "area": "港区",
        "name": "芝浦アイランド グローヴタワー",
        "spec": "28階 / 65.40㎡ / 2LDK / 東 / 築19年",
        "source": "ノムコム",
        "area_sqm": 65.40,
        "market_tsubo": 620.0,
        "revision_count": 2,
        "current_price": 12180,
        "previous_price": 12980,
        "elapsed_days": 110,
        "notes": "自己居住用・現空"
    },
    {
        "area": "港区",
        "name": "シティタワー品川",
        "spec": "31階 / 84.14㎡ / 3LDK / 南東 / 築18年",
        "source": "すみふの仲介ステップ",
        "area_sqm": 84.14,
        "market_tsubo": 430.0,
        "revision_count": 3,
        "current_price": 10800,
        "previous_price": 11500,
        "elapsed_days": 42,
        "notes": "空室引き渡し"
    },
    {
        "area": "港区",
        "name": "パークコート赤坂 ザ タワー",
        "spec": "15階 / 58.20㎡ / 1LDK / 西 / 築17年",
        "source": "三井のリハウス",
        "area_sqm": 58.20,
        "market_tsubo": 900.0,
        "revision_count": 1,
        "current_price": 16800,
        "previous_price": 17800,
        "elapsed_days": 85,
        "notes": "居住中・引渡相談"
    },
    # --- 中央区 ---
    {
        "area": "中央区",
        "name": "勝どき ザ・タワー",
        "spec": "35階 / 71.20㎡ / 3LDK / 南 / 築10年",
        "source": "三井のリハウス",
        "area_sqm": 71.20,
        "market_tsubo": 650.0,
        "revision_count": 2,
        "current_price": 13800,
        "previous_price": 14500,
        "elapsed_days": 68,
        "notes": "空室"
    },
    {
        "area": "中央区",
        "name": "パークタワー勝どき サウス",
        "spec": "19階 / 60.50㎡ / 2LDK / 北東 / 築2年",
        "source": "東急リバブル",
        "area_sqm": 60.50,
        "market_tsubo": 720.0,
        "revision_count": 1,
        "current_price": 13480,
        "previous_price": 14200,
        "elapsed_days": 35,
        "notes": "未入居・即引渡可"
    },
    # --- 江東区 ---
    {
        "area": "江東区",
        "name": "シティタワーズ豊洲ザ・ツイン サウスタワー",
        "spec": "42階 / 54.50㎡ / 1LDK / 北 / 築17年",
        "source": "すみふの仲介ステップ",
        "area_sqm": 54.50,
        "market_tsubo": 630.0,
        "revision_count": 2,
        "current_price": 10600,
        "previous_price": 11800,
        "elapsed_days": 276,
        "notes": "現空"
    }
]

def main():
    os.makedirs("data", exist_ok=True)
    wards = ["千代田区", "中央区", "港区", "新宿区", "文京区", "台東区", "墨田区", "江東区", 
             "品川区", "目黒区", "大田区", "世田谷区", "渋谷区", "中野区", "杉並区", "豊島区", 
             "北区", "荒川区", "板橋区", "練馬区", "足立区", "葛飾区", "江戸川区"]

    # 区ごとに分割して処理
    for ward in wards:
        ward_items = []
        for item in MASTER_DATA:
            if item["area"] != ward:
                continue

            # 実需フィルター：オーナーチェンジ文言のチェック
            target_text = f"{item['name']} {item['spec']} {item.get('notes', '')}"
            if any(kw in target_text for kw in INVESTMENT_EXCLUDE_WORDS):
                continue  # 投資用は破棄

            before = item["previous_price"]
            after = item["current_price"]
            diff = after - before

            if diff < 0:
                diff_rate = round((diff / before) * 100, 2)
                before_tsubo = calc_tsubo(before, item["area_sqm"])
                after_tsubo = calc_tsubo(after, item["area_sqm"])

                ward_items.append({
                    "area": item["area"],
                    "elapsedDays": item["elapsed_days"],
                    "revisionCount": item.get("revision_count", 1),
                    "marketTsubo": item.get("market_tsubo", 600.0),
                    "name": item["name"],
                    "spec": item["spec"],
                    "beforePrice": f"{before:,}万",
                    "beforeTsubo": f"{before_tsubo}万/坪",
                    "afterPrice": f"{after:,}万",
                    "afterTsubo": f"{after_tsubo}万/坪",
                    "diffPrice": f"{diff:,}万",
                    "diffRate": f"({diff_rate}%)",
                    "source": item["source"],
                    "searchWord": f"{item['name']} {item['source']}"
                })

        # data/data_港区.json のように個別出力
        output_payload = {
            "ward": ward,
            "updatedAt": today_str,
            "properties": ward_items
        }
        with open(f"data/data_{ward}.json", "w", encoding="utf-8") as f:
            json.dump(output_payload, f, ensure_ascii=False, indent=2)

    print("Successfully generated isolated ward data files without investment properties.")

if __name__ == "__main__":
    main()
