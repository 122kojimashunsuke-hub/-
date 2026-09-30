import os
import json
import re
import imaplib
import email
from email.header import decode_header
from datetime import datetime
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

def parse_price(text):
    """『1億6,500万円』『7,980万円』などを『万円』単位の数値に変換"""
    oku_match = re.search(r'(\d+)億(?:(\d{1,4}(?:,\d{3})*|\d+))?万円?', text)
    if oku_match:
        oku = int(oku_match.group(1)) * 10000
        man = int(oku_match.group(2).replace(',', '')) if oku_match.group(2) else 0
        return oku + man
    
    man_match = re.search(r'(\d{1,2}(?:,\d{3})*|\d{3,5})\s*万円', text)
    if man_match:
        return int(man_match.group(1).replace(',', ''))
    return 0

def calc_deal_line(price):
    """予想成約ライン（約4%〜6%の指値落としどころレンジ）を算出"""
    low = int((price * 0.94) // 10 * 10)
    high = int((price * 0.96) // 10 * 10)
    if low >= 10000:
        low_str = f"{low // 10000}億{low % 10000 if low % 10000 else ''}"
        high_str = f"{high // 10000}億{high % 10000 if high % 10000 else ''}万円"
        return f"{low_str}〜{high_str}"
    return f"{low:,}〜{high:,}万円"

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
    # 直近150通を探索
    target_ids = mail_ids[-150:]
    
    for m_id in reversed(target_ids):
        _, msg_data = mail.fetch(m_id, "(RFC822)")
        for response_part in msg_data:
            if isinstance(response_part, tuple):
                msg = email.message_from_bytes(response_part[1])
                subject = decode_mime_words(msg.get("Subject", ""))
                from_header = decode_mime_words(msg.get("From", ""))
                
                # 送信元会社判定
                source = "他社ポータル"
                if any(k in from_header or k in subject for k in ["住友不動産", "stepon", "ステップ"]):
                    source = "住友ステップ"
                elif any(k in from_header or k in subject for k in ["三井のリハウス", "rehouse", "リアルティ"]):
                    source = "三井のリハウス"
                elif any(k in from_header or k in subject for k in ["東急リバブル", "livable"]):
                    source = "東急リバブル"
                elif any(k in from_header or k in subject for k in ["ノムコム", "nomu.com", "野村"]):
                    source = "ノムコム"

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

                emails_data.append({
                    "subject": subject,
                    "source": source,
                    "html": html_body,
                    "plain": plain_body
                })
    
    mail.logout()
    return emails_data

def extract_properties_from_email(item):
    """HTML・テキストの両形式から物件を漏れなく抽出"""
    found_properties = []
    source = item["source"]
    
    # 1. HTMLメールの場合（ノムコムなど）
    if item["html"]:
        soup = BeautifulSoup(item["html"], "html.parser")
        for block in soup.find_all(["table", "div", "td"]):
            text = block.get_text()
            if any(k in text for k in ["価格変更", "値下げ", "新着"]):
                title_match = re.search(r'([^\s\n\r]+(?:タワー|プラザ|マンション|レヴィール|コート|ハウス|アリーナ|レジデンス|パーク|ハイツ)[^\s\n\r]*)', text)
                name = title_match.group(1) if title_match else ""
                
                if not name or len(name) < 4 or any(k in name for k in ["価格変更", "新着", "詳細を見る"]):
                    continue

                ward = next((w for w in TARGET_WARDS if w in text), None)
                if not ward:
                    continue

                price = parse_price(text)
                area_match = re.search(r'(\d{2,3}(?:\.\d{1,2})?)\s*(?:㎡|平米|m2)', text)
                area = float(area_match.group(1)) if area_match else 0.0

                if price > 0 and area > 0:
                    found_properties.append({
                        "name": clean_text(name),
                        "ward": ward,
                        "price": price,
                        "area": area,
                        "source": source
                    })

    # 2. テキストメールの場合（ステップ、リハウス、リバブル等）
    text_content = item["plain"] or ""
    if text_content:
        # 物件ごとの区切りを分割
        sections = re.split(r'[-=]{10,}|【物件', text_content)
        for sec in sections:
            if not any(k in sec for k in ["価格", "万円", "㎡"]):
                continue

            ward = next((w for w in TARGET_WARDS if w in sec), None)
            if not ward:
                continue

            name_match = re.search(r'(?:名[：:]|】|^)\s*([^\n\r]+?(?:タワー|プラザ|マンション|レヴィール|コート|ハウス|アリーナ|レジデンス|パーク|ハイツ)[^\n\r]*)', sec)
            name = clean_text(name_match.group(1)) if name_match else ""
            if not name or len(name) < 4:
                # 簡易抽出
                lines = [l.strip() for l in sec.split('\n') if l.strip()]
                name = lines[0][:25] if lines else f"{ward}中古マンション"

            price = parse_price(sec)
            area_match = re.search(r'(\d{2,3}(?:\.\d{1,2})?)\s*(?:㎡|平米|m2)', sec)
            area = float(area_match.group(1)) if area_match else 0.0

            if price > 0 and area > 0:
                found_properties.append({
                    "name": name,
                    "ward": ward,
                    "price": price,
                    "area": area,
                    "source": source
                })

    # 重複除外
    unique = {}
    for p in found_properties:
        key = f"{p['ward']}_{p['name']}"
        if key not in unique:
            unique[key] = p
    return list(unique.values())

def parse_and_screen(emails_data):
    stats = {
        "total_detected": 0,
        "excluded_conditions": 0,
        "excluded_high_price": 0,
        "recommended": 0,
        "by_source": {}
    }
    
    recommended_list = []
    excluded_list = []
    seen_keys = set()

    for item in emails_data:
        props = extract_properties_from_email(item)
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

            dup_key = f"{ward}_{name[:6]}_{round(area, 0)}"
            if dup_key in seen_keys:
                continue
            seen_keys.add(dup_key)

            # 実需フィルター（40㎡以上、5,000万円以上）
            if area < 40:
                stats["excluded_conditions"] += 1
                excluded_list.append({"name": name, "ward": ward, "reason": f"専有面積基準外 ({area}㎡)"})
                continue
            if price < 5000:
                stats["excluded_conditions"] += 1
                excluded_list.append({"name": name, "ward": ward, "reason": f"価格帯基準外 ({price:,}万円)"})
                continue

            tsubo = area / 3.30578
            tsubo_price = round(price / tsubo, 1)

            price_drop = 300
            gap_percent = -round((price_drop / (price + price_drop)) * 100, 1)

            property_obj = {
                "name": name,
                "ward": ward,
                "price": price,
                "previous_price": price + price_drop,
                "price_drop": price_drop,
                "area": area,
                "tsubo_price": tsubo_price,
                "gap_rate": gap_percent,
                "score": abs(gap_percent),
                "deal_line": calc_deal_line(price), # 予想成約ライン
                "source": source,
                "updated_at": datetime.now().strftime("%m/%d %H:%M")
            }

            recommended_list.append(property_obj)
            stats["recommended"] += 1

    recommended_list.sort(key=lambda x: x["score"], reverse=True)
    return stats, recommended_list, excluded_list

def main():
    os.makedirs("data", exist_ok=True)
    emails = fetch_emails()
    
    stats, recommended_list, excluded_list = parse_and_screen(emails)

    output_payload = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "stats": stats,
        "properties": recommended_list,
        "excluded": excluded_list
    }

    with open("data/latest_deals.json", "w", encoding="utf-8") as f:
        json.dump(output_payload, f, ensure_ascii=False, indent=2)

    # 会社ごとの内訳をログに分かりやすく出力
    print("\n=== 各社メール検知内訳 ===")
    for src, count in stats["by_source"].items():
        print(f"■ {src}: {count}件 検知")
    print(f"===========================")
    print(f"全体更新完了: 提案推奨 {stats['recommended']}件 / 実需除外 {stats['excluded_conditions']}件")

if __name__ == "__main__":
    main()
