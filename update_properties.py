import os
import json
import re
from datetime import datetime
import pytz

jst = pytz.timezone('Asia/Tokyo')
now = datetime.now(jst)
today_str = now.strftime('%Y年%-m月%-d日（%a）')

# 投資用・オーナーチェンジ排除キーワード
INVESTMENT_EXCLUDE_WORDS = [
    "オーナーチェンジ", "賃貸中", "利回り", "表面利回り", 
    "想定利回り", "想定年収", "現況：賃貸", "投資用", "借家"
]

# 不動産広告表示規約・宅建業法上の禁止・要注意ワード（スクリーニングリスト）
PROHIBITED_WORDS = [
    "資産価値", "希少", "希少性", "出口", "確実", "絶対", "最高", 
    "格安", "激安", "買得", "お買い得", "破格", "完売", "早い者勝ち", 
    "特選", "日本一", "完璧", "将来性", "値上がり", "儲かる", "鉄板"
]

def calc_tsubo(price_man, area_sqm):
    try:
        tsubo = area_sqm / 3.30578
        return round(price_man / tsubo, 1)
    except:
        return 0.0

def screen_text(text):
    cleaned_text = text
    replacements = {
        "資産価値": "棟内の流通性",
        "希少性": "募集頻度の少なさ",
        "希少": "募集頻度の低い",
        "出口": "将来の住み替え時の選択肢",
        "格安": "成約相場と同水準",
        "お買い得": "現実的な成約ライン",
        "早い者勝ち": "反響の動き出しが早い"
    }

    for ng_word, safe_word in replacements.items():
        cleaned_text = re.sub(ng_word, safe_word, cleaned_text)

    for word in PROHIBITED_WORDS:
        if word in cleaned_text:
            cleaned_text = cleaned_text.replace(word, "")

    return cleaned_text

def build_proposals_by_axis(item):
    """
    社内CRMの検索軸（エリア・予算・面積・間取り）に合わせた4パターンの提案文を生成
    """
    name = item["name"]
    spec = item["spec"]
    new_price = f"{item['current_price']:,}万円"
    old_price = f"{item['previous_price']:,}万円"
    tsubo = item["after_tsubo"]
    market_tsubo = item["market_tsubo"]
    diff_price = f"{abs(item['current_price'] - item['previous_price']):,}万円"
    area = item["area"]
    sqm = item["area_sqm"]

    # 間取り表記の抽出（例: 2LDK）
    layout_match = re.search(r'([1-4][LDK]+)', spec)
    layout_str = layout_match.group(1) if layout_match else "居住用"

    # 4つの軸ごとの所感テキスト
    approaches = {
        "area": {
            "title": "📍 エリアアプローチ",
            "crm_hint": f"{area}エリア限定で探されている顧客向け",
            "comment": f"直近で▲{diff_price}の改定が入りました。同エリア・同規模住戸の直近取引平仄（坪{market_tsubo}万円前後）と比較しても乖離が縮小し、実勢相場と平仄が合う成約ターゲット圏にしっかり入ってきた印象です。同エリア内での比較検討において現実的な判断材料となる住戸です。"
        },
        "budget": {
            "title": "💰 予算アプローチ",
            "crm_hint": f"予算{round(item['current_price']/1000, 1)}億円前後（上限{new_price}）で探されている顧客向け",
            "comment": f"本日▲{diff_price}の条件改定が入り、改定後価格{new_price}（坪約{tsubo}万円）となりました。同棟における直近成約水準（坪{market_tsubo}万円前後）と合致する水準まで価格調整が行われたため、ご予算枠内において現実的にご検討いただける検討ラインに到達いたしました。"
        },
        "area_size": {
            "title": "📐 面積アプローチ",
            "crm_hint": f"専有面積{int(sqm)}㎡台（広さ優先）で探されている顧客向け",
            "comment": f"専有面積{sqm}㎡の居住空間を確保した住戸において、直近で▲{diff_price}の改定が入りました。同規模住戸の実勢成約平仄（坪{market_tsubo}万円前後）と突き合わせても面積あたりの単価バランスが市場水準に収束し、ゆとりある住空間と価格の整合性が取れた水準です。"
        },
        "layout": {
            "title": "🚪 間取りアプローチ",
            "crm_hint": f"{layout_str}指定（部屋数・動線優先）で探されている顧客向け",
            "comment": f"居住用として需要の厚い{layout_str}住戸において、直近で▲{diff_price}の条件改定がございました。居室配置や生活動線のバランスが良い住戸であり、周辺の同間取り成約事例（坪{market_tsubo}万円前後）と比較しても実需目線で現実的な検討ラインに入ってまいりました。"
        }
    }

    result = {}
    for key, data in approaches.items():
        raw_body = f"""〇〇様
いつも大変お世話になっております。

ご希望条件に近い注目住戸におきまして、本日付で条件改定（価格変更）の動きがございましたので速報として共有いたします。

━━━━━━━━━━━━━━━━━━━━━━━━━━
【物件概要】
・{name}
・改定後価格：{new_price}（坪単価：約{tsubo}万円）※旧価格：{old_price}
・専有スペック：{spec}
━━━━━━━━━━━━━━━━━━━━━━━━━━

【担当からのマーケット所見】
{data['comment']}

条件改定直後はポータルサイト等での反響の動き出しが早まる傾向がございます。詳細な販売図面や過去の成約履歴一覧を取り急ぎ手配いたしますので、ご興味がございましたらお申し付けください。"""

        safe_body = screen_text(raw_body)
        safe_subject = screen_text(f"【条件改定速報】{name}（成約相場平仄ラインへの価格変更）")

        result[key] = {
            "title": data["title"],
            "crmHint": data["crm_hint"],
            "subject": safe_subject,
            "body": safe_body.strip()
        }

    return result

# 追跡マスターデータ（直近成約事例エビデンス付き）
MASTER_DATA = [
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
        "notes": "自己居住用・現空",
        # 根拠データ
        "evidence_deal": "2026年3月成約 / 26階 東向 / 坪618万円",
        "evidence_range": "坪 600万 〜 635万円（直近6ヶ月・3件）",
        "evidence_note": "26階東向き（同方位・近似階）の成約実績と平仄合致。妥当性高。"
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
        "notes": "空室引き渡し",
        # 根拠データ
        "evidence_deal": "2026年5月成約 / 30階 南向 / 坪428万円",
        "evidence_range": "坪 415万 〜 445万円（直近1年・4件）",
        "evidence_note": "定期借地権残年数考慮済。30階南向きの直近成約とほぼ同水準。"
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
        "notes": "居住中",
        # 根拠データ
        "evidence_deal": "2026年1月成約 / 14階 西向 / 坪895万円",
        "evidence_range": "坪 880万 〜 930万円（直近半年・2件）",
        "evidence_note": "14階西向きとほぼ同位置。坪900万近辺は直近実勢と合致。"
    }
]

def main():
    os.makedirs("data", exist_ok=True)
    wards = ["港区", "中央区", "江東区", "千代田区", "渋谷区", "新宿区", "北区"]

    for ward in wards:
        ward_items = []
        for item in MASTER_DATA:
            if item["area"] != ward:
                continue

            target_text = f"{item['name']} {item['spec']} {item.get('notes', '')}"
            if any(kw in target_text for kw in INVESTMENT_EXCLUDE_WORDS):
                continue

            before = item["previous_price"]
            after = item["current_price"]
            diff = after - before

            if diff < 0:
                diff_rate = round((diff / before) * 100, 2)
                before_tsubo = calc_tsubo(before, item["area_sqm"])
                after_tsubo = calc_tsubo(after, item["area_sqm"])
                item["after_tsubo"] = after_tsubo

                diff_from_market = ((after_tsubo - item["market_tsubo"]) / item["market_tsubo"]) * 100

                prop_data = {
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
                    "searchWord": f"{item['name']} {item['source']}",
                    # エビデンス項目
                    "evidenceDeal": item.get("evidence_deal", "確認中"),
                    "evidenceRange": item.get("evidence_range", "確認中"),
                    "evidenceNote": item.get("evidence_note", "社内DB・レインズで要確認")
                }

                if diff_from_market <= 3.0:
                    prop_data["proposals"] = build_proposals_by_axis(item)

                ward_items.append(prop_data)

        with open(f"data/data_{ward}.json", "w", encoding="utf-8") as f:
            json.dump({"ward": ward, "updatedAt": today_str, "properties": ward_items}, f, ensure_ascii=False, indent=2)

    print("Complete: Generated ward files with evidence and 4-axis proposals.")

if __name__ == "__main__":
    main()
