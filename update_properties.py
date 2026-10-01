import os
import json
import re
import imaplib
import email
from email.header import decode_header
from datetime import datetime
import time
import urllib.parse
import urllib.request
from bs4 import BeautifulSoup

TARGET_WARDS = [
    "千代田区", "中央区", "港区", "新宿区", "文京区", "台東区", "墨田区", "江東区",
    "品川区", "目黒区", "大田区", "世田谷区", "渋谷区", "中野区", "杉並区", "豊島区",
    "北区", "荒川区", "板橋区", "練馬区", "足立区", "葛飾区", "江戸川区"
]

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip()

def decode_mime_words(s):
    if not s:
        return ""
    decoded_fragments = decode_header(s)
    res = []
    for fragment, encoding in decoded_fragments:
        if isinstance(fragment, bytes):
            res.append(fragment.decode(encoding or 'utf-8', errors='ignore'))
        else:
            res.append(str(fragment))
    return "".join(res)

def format_price_yen(val):
    if val >= 10000:
        oku = val // 10000
        man = val % 10000
        return f"{oku}億{f'{man:,}万' if man > 0 else ''}円"
    return f"{val:,}万円"

def calc_deal_line(price):
    low = int((price * 0.94) // 10 * 10)
    high = int((price * 0.96) // 10 * 10)
    return f"{format_price_yen(low)}〜{format_price_yen(high)}"

def fetch_emails():
    user = os.environ.get("GMAIL_USER")
    app_pass = os.environ.get("GMAIL_APP_PASS")

    if not user or not app_pass:
        print("GMAIL_USER または GMAIL_APP_PASS が未設定です。")
        return []

    print("=== ポータルメール巡回開始 ===")
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(user, app_pass)
    mail.select("inbox")

    status, messages = mail.search(None, 'ALL')
    if status != "OK" or not messages[0]:
        mail.logout()
        return []

    mail_ids = messages[0].split()
    print(f"受信トレイの総メール数: {len(mail_ids)}通")

    emails_data = []
    target_ids = mail_ids[-200:]
    mail_source_counts = {}

    for m_id in reversed(target_ids):
        _, msg_data = mail.fetch(m_id, "(RFC822)")
        for response_part in msg_data:
            if isinstance(response_part, tuple):
                msg = email.message_from_bytes(response_part[1])
                subject = decode_mime_words(msg.get("Subject", ""))
                from_header = decode_mime_words(msg.get("From", ""))
                header_text = (from_header + " " + subject).lower()

                source = None
                if any(k in header_text for k in ["住友不動産", "stepon", "ステップ"]):
                    source = "住友ステップ"
                elif any(k in header_text for k in ["三井のリハウス", "rehouse", "リアルティ"]):
                    source = "三井のリハウス"
                elif any(k in header_text for k in ["東急リバブル", "livable", "tokyu", "myliv"]):
                    source = "東急リバブル"
                elif any(k in header_text for k in ["ノムコム", "nomu.com", "野村"]):
                    source = "ノムコム"

                if not source:
                    continue

                html_body = ""
                plain_body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        ctype = part.get_content_type()
                        payload = part.get_payload(decode=True)
                        if not payload:
                            continue
                        charset = part.get_content_charset() or 'utf-8'
                        if ctype == "text/html":
                            html_body = payload.decode(charset, errors='ignore')
                        elif ctype == "text/plain":
                            plain_body = payload.decode(charset, errors='ignore')
                else:
                    payload = msg.get_payload(decode=True)
                    charset = msg.get_content_charset() or 'utf-8'
                    if payload:
                        plain_body = payload.decode(charset, errors='ignore')

                text_content = ""
                if html_body:
                    soup = BeautifulSoup(html_body, "html.parser")
                    text_content = soup.get_text(separator="\n")
                else:
                    text_content = plain_body

                # 【防衛策1】価格変更関連の語句が一切ないメールはAPI節約のため事前に除外
                full_check_text = subject + " " + text_content
                if not any(k in full_check_text for k in ["価格", "値下げ", "改定", "変更", "新価格"]):
                    continue

                mail_source_counts[source] = mail_source_counts.get(source, 0) + 1

                emails_data.append({
                    "subject": subject,
                    "source": source,
                    "text": text_content
                })
    
    mail.logout()
    print("=== 解析対象メール件数（値下げ関連） ===")
    for src, c in mail_source_counts.items():
        print(f"・{src}: {c}通")
    print("=======================================")
    return emails_data

def extract_properties_with_gemini(email_item, api_key):
    """Gemini 2.5 Flash を使用して人間同等の文脈理解で物件をJSON抽出"""
    prompt = f"""
あなたは日本の不動産ポータルサイト（三井のリハウス、住友ステップ、東急リバブル、ノムコム）からの通知メールを解析するプロフェッショナルです。
以下のメール本文を読み、『価格改定（値下げ、価格変更、新価格、価格更新）』されたマンション物件のみを抽出してJSON形式で出力してください。

【厳格な抽出ルール】
1. 『新着物件』や『単なる紹介物件』は絶対に抽出しないでください。値下げ・価格改定された物件のみが対象です。
2. メールの末尾や途中にある『保存した検索条件』や案内文、注意書きから数値を抽出しないでください。
3. 物件名、東京23区の区名、新価格（万円単位の数値）、旧価格（万円単位の数値、記載がなければnull）、専有面積（平米・㎡の数値）を正確に読み取ってください。
4. 価格の単位変換例: 『1億780万円』→ 10780, 『7,980万円』→ 7980, 『1億4,500万円』→ 14500。
5. 面積の変換例: 『65.09平米』『65.09㎡』『65.09m²』→ 65.09。

【対象区名】
千代田区, 中央区, 港区, 新宿区, 文京区, 台東区, 墨田区, 江東区, 品川区, 目黒区, 大田区, 世田谷区, 渋谷区, 中野区, 杉並区, 豊島区, 北区, 荒川区, 板橋区, 練馬区, 足立区, 葛飾区, 江戸川区

【出力JSONスキーマ】
[
  {{
    "name": "物件名（例: プレミスト有明ガーデンズ）",
    "ward": "区名（例: 江東区）",
    "price": 10780,
    "previous_price": 11500,
    "area": 65.09
  }}
]
該当物件が1件もない場合は空配列 `[]` を返してください。Markdownのコードブロック（```json）は不要です。純粋なJSON文字列のみを出力してください。

【メール送信元】
{email_item['source']}

【メール本文】
{email_item['text'][:6000]}
"""

# 1. URLとヘッダーの設定（ヘッダーで安全にAPIキーを渡す方式）
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.0-flash:generateContent"
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key.strip()
    }
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.0
        }
    }

    # 2. data引数を渡して確実にPOST送信にする
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers
    )

    # 3. リクエスト実行とエラーボディの詳細出力
    try:
        with urllib.request.urlopen(req) as res:
            res_data = json.loads(res.read().decode("utf-8"))
            text = res_data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"=== Gemini API HTTPエラー ({email_item.get('source', '')}) ===")
        print(f"Status Code: {e.code}")
        print(f"Error Body: {error_body}")
        return []
    except Exception as e:
        print(f"Gemini API抽出エラー ({email_item.get('source', '')}): {e}")
        return []

def parse_and_screen(emails_data, api_key):
    stats = {
        "total_detected": 0,
        "excluded_conditions": 0,
        "recommended": 0,
        "by_source": {}
    }
    
    properties_dict = {}
    excluded_list = []

    for item in emails_data:
        props = extract_properties_with_gemini(item, api_key)
        # 【防衛策2】APIレート制限（429）を回避するための安全ウェイト
        time.sleep(1.0)

        if not props:
            continue

        stats["total_detected"] += len(props)
        stats["by_source"][item["source"]] = stats["by_source"].get(item["source"], 0) + len(props)

        for p in props:
            ward = p["ward"]
            name = p["name"]
            price = p["price"]
            area = p["area"]
            source = p["source"]

            # 実需フィルター（40㎡未満、5,000万円未満の除外）
            if area < 40:
                stats["excluded_conditions"] += 1
                excluded_list.append({
                    "name": name, "ward": ward, "price": price, "area": area,
                    "source": source, "reason": f"専有面積基準外 ({area}㎡ < 40㎡)"
                })
                continue
            if price < 5000:
                stats["excluded_conditions"] += 1
                excluded_list.append({
                    "name": name, "ward": ward, "price": price, "area": area,
                    "source": source, "reason": f"価格帯基準外 ({format_price_yen(price)} < 5,000万円)"
                })
                continue

            # 名寄せ・重複マージ（最安値採用＋会社名マージ）
            key = f"{ward}_{name}_{area}"
            
            if key in properties_dict:
                existing = properties_dict[key]
                sources = existing["source"].split(" / ")
                if source not in sources:
                    sources.append(source)
                    existing["source"] = " / ".join(sources)
                if price < existing["price"]:
                    existing["price"] = price
                    existing["deal_line"] = calc_deal_line(price)
                    existing["tsubo_price"] = round(price / (area / 3.30578), 1)
                    if p["previous_price"]:
                        existing["previous_price"] = p["previous_price"]
                        existing["price_drop"] = p["price_drop"]
                        existing["gap_rate"] = p["gap_rate"]
                continue

            tsubo = area / 3.30578
            tsubo_price = round(price / tsubo, 1)
            map_query = urllib.parse.quote(f"{ward} {name}")
            google_map_url = f"https://www.google.com/maps/search/?api=1&query={map_query}"

            properties_dict[key] = {
                "name": name,
                "ward": ward,
                "price": price,
                "previous_price": p["previous_price"],
                "price_drop": p["price_drop"],
                "gap_rate": p["gap_rate"],
                "area": area,
                "tsubo_price": tsubo_price,
                "deal_line": calc_deal_line(price),
                "google_map_url": google_map_url,
                "source": source,
                "detected_at": datetime.now().strftime("%m/%d %H:%M")
            }

    recommended_list = list(properties_dict.values())
    stats["recommended"] = len(recommended_list)

    return stats, recommended_list, excluded_list

def main():
    os.makedirs("data", exist_ok=True)
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("エラー: GEMINI_API_KEY が環境変数に設定されていません。")
        return

    emails = fetch_emails()
    stats, recommended_list, excluded_list = parse_and_screen(emails, api_key)

    output_payload = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "stats": stats,
        "properties": recommended_list,
        "excluded": excluded_list
    }

    with open("data/latest_deals.json", "w", encoding="utf-8") as f:
        json.dump(output_payload, f, ensure_ascii=False, indent=2)

    print("\n=== 各社メール検知内訳 ===")
    for src, count in stats["by_source"].items():
        print(f"■ {src}: {count}件 検知")
    print("===========================")
    print(f"全体更新完了: 提案推奨 {stats['recommended']}件 / 実需除外 {stats['excluded_conditions']}件")

if __name__ == "__main__":
    main()
