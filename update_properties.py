import os
import json
import re
from datetime import datetime
import pytz

jst = pytz.timezone('Asia/Tokyo')
today_str = datetime.now(jst).strftime('%Y年%-m月%-d日（%a）')

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
    """
    文章内の広告表示規約違反リスクのある単語を完全検知・スクリーニングする関数
    """
    cleaned_text = text
    # 表現の安全な言い換えマッピング
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

    # それでも残っている禁止ワードがあれば検知・強制削除
    for word in PROHIBITED_WORDS:
        if word in cleaned_text:
            cleaned_text = cleaned_text.replace(word, "")

    return cleaned_text

def generate_safe_proposal_email(item, diff_from_market):
    """
    成約圏内に入った実需物件に特化した、コンプライアンス準拠の提案メール生成
    """
    name = item["name"]
    spec = item["spec"]
    price = f"{item['current_price']:,}万円"
    tsubo = item["after_tsubo"]
    market_tsubo = item["market_tsubo"]
    diff_price = f"{abs(item['current_price'] - item['previous_price']):,}万円"
    days = item["elapsed_days"]
    rev_count = item.get("revision_count", 1)

    # 1. 想定顧客ペルソナ判定（間取り・平米・価格帯から自動分類）
    sqm = item["area_sqm"]
    if sqm < 60:
        target_persona = "都心DINKS・単身実需層（予算1.3億〜1.8億 / 利便性・棟内流通性重視）"
        persona_hook = "単身〜DINKS層の実需検討において、生活動線および棟内での流通実績が多い間取り規模です。"
    else:
        target_persona = "30〜40代実需ファミリー層（自己居住用 / 2LDK〜3LDK検討中）"
        persona_hook = "ご家族構成の変化にも対応しやすく、居住用として最も問い合わせの厚い専有面積ゾーンです。"

    # 2. 売出期間・改定回数に応じた市場所見
    if days >= 90 or rev_count >= 2:
        market_comment = (
            f"募集開始から一定の期間（売出{days}日目・今回で{rev_count}回目の改定）を経て、"
            f"直近で▲{diff_price}の条件改定が入りました。売主様側も本格的に成約を見据えた現実的な募集条件へ移行した印象です。"
        )
    else:
        market_comment = (
            f"直近で▲{diff_price}の改定が行われ、同棟の直近取引平仄（成約相場：約{market_tsubo}万/坪）と"
            f"整合する成約ターゲット圏に突入いたしました。"
        )

    # 3. メール本文の生成（客観的ファクト構成）
    raw_body = f"""いつも大変お世話になっております。

ご希望条件に近い注目物件におきまして、本日付で条件改定（価格変更）の動きがございましたので速報として共有いたします。

━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 物件概要：{name}
■ 専有スペック：{spec}
■ 改定後価格：{price}（坪単価：約{tsubo}万/坪）
━━━━━━━━━━━━━━━━━━━━━━━━━━

【マーケット所見・相場分析】
{market_comment}
{persona_hook}

同エリア・同規模住戸の直近成約水準（坪{market_tsubo}万円前後）と突き合わせても、実勢相場との乖離が縮小し、現実的なご検討ラインに入ってきたと判断しております。

条件改定直後はポータルサイト等での反響の動き出しが早まる傾向がございます。詳細な販売図面や過去の成約履歴一覧を取り急ぎ手配いたしますので、ご興味がございましたらお申し付けください。
"""

    # 4. スクリーニングフィルターを適用
    safe_body = screen_text(raw_body)
    safe_subject = screen_text(f"【条件改定速報】{name}（成約相場平仄ラインへの価格変更）")

    return {
        "targetPersona": target_persona,
        "emailSubject": safe_subject,
        "emailBody": safe_body.strip()
    }

# 追跡マスターデータ
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
        "notes": "居住中"
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

            # 実需フィルター
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

                # 相場乖離率
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
                    "searchWord": f"{item['name']} {item['source']}"
                }

                # 成約圏内（相場比 +3%以内）の場合のみ提案メールを自動生成
                if diff_from_market <= 3.0:
                    proposal = generate_safe_proposal_email(item, diff_from_market)
                    prop_data["proposal"] = proposal

                ward_items.append(prop_data)

        with open(f"data/data_{ward}.json", "w", encoding="utf-8") as f:
            json.dump({"ward": ward, "updatedAt": today_str, "properties": ward_items}, f, ensure_ascii=False, indent=2)

    print("Complete: Generated ward files with compliant proposal emails.")

if __name__ == "__main__":
    main()
