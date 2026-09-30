import os
import json
import re
import imaplib
import email
from email.header import decode_header
from datetime import datetime
import urllib.parse
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
    oku_match = re.search(r'(\d+)\s*億(?:(\d{1,4}(?:,\d{3})*|\d+))?\s*万円?', text)
    if oku_match:
        oku = int(oku_match.group(1)) * 10000
        man = int(oku_match.group(2).replace(',', '')) if oku_match.group(2) else 0
        return oku + man
    
    man_match = re.search(r'(\d{1,2}(?:,\d{3})*|\d{3,5})\s*万円', text)
    if man_match:
        return int(man_match.group(1).replace(',', ''))
    return 0

def format_price_yen(val):
    """金額数値を正しい日本語表記（〇億〇〇万円）にフォーマット"""
    if val >= 10000:
        oku = val // 10000
        man = val % 10000
        return f"{oku}億{f'{man:,}万' if man > 0 else ''}円"
    return f"{val:,}万円"

def calc_deal_line(price):
    """予想成約ライン（約4%〜6%の指値落としどころレンジ）を算出（※logic.md暫定仮置き）"""
    low = int((price * 0.94) // 10 * 10)
    high = int((price * 0.96) // 10 * 10)
    return f"{format_price_yen(low)}〜{format_price_yen(high)}"

def parse_price_change(text):
    """メール本文から新旧価格を抽出。なければNone（new_p も返却）"""
    patterns = [
        r'(?:旧価格|改定前|変更前)[：:\s]*(\d+.*万円?).*?(?:新価格|改定後|変更後)[：:\s]*(\d+.*万円?)',
        r'(\d+.*万円?)\s*(?:[→~〜]|から)\s*(?:新価格[：:\s]*)?(\d+.*万円?)'
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            old_p = parse_price(m.group(1))
            new_p = parse_price(m.group(2))
            if old_p > new_p and new_p > 0:
                drop = old_p - new_p
                rate = -round((drop / old_p) * 100, 1)
                return old_p, new_p, drop, rate
    return None, None, None, None

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
    target_ids = mail_ids[-150:]
    
    for m_id in reversed(target_ids):
        _, msg_data = mail.fetch(m_id, "(RFC822)")
        for response_part in msg_data:
            if isinstance(response_part, tuple):
                msg = email.message_from_bytes(response_part[1])
                subject = decode_mime_words(msg.get("Subject", ""))
                from_header = decode_mime_words(msg.get("From", ""))
                
                # 修正①：小文字化して大文字・小文字ブレを完全排除
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

                emails_data.append({
                    "subject": subject,
                    "source": source,
                    "html": html_body,
                    "plain": plain_body
                })
    
    mail.logout()
    return emails_data

def extract_properties_from_email(item):
    found_properties = []
    source = item["source"]
    
    # 1. HTMLメール解析（ノムコム、東急リバブル等）
    if item["html"]:
        soup = BeautifulSoup(item["html"], "html.parser")
        for block in soup.find_all(["table", "div"]):
            text = block.get_text()
            if any(k in text for k in ["価格変更", "値下げ", "新価格"]):
                name = ""
                name_el = block.find(["a", "h3", "h4", "strong", "b"])
                if name_el:
                    candidate = clean_text(name_el.get_text())
                    if len(candidate) >= 3 and not any(k in candidate for k in ["価格変更", "詳細", "POINT", "新着", "新価格", "画像追加"]):
                        name = candidate

                if not name or len(name) < 3:
                    continue

                ward = next((w for w in TARGET_WARDS if w in text), None)
                if not ward:
                    continue

                # 修正②：新価格（new_p）が存在する場合は最優先で代入
                old_p, new_p, drop, rate = parse_price_change(text)
                if new_p:
                    price = new_p
                else:
                    price_match = re.search(r'(?:新価格[：:\s\d/]*|新価格[：:\s]*)?(\d+.*万円?)', text)
                    price = parse_price(price_match.group(1)) if price_match else 0

                # 面積抽出（m², ㎡, 平米, m2 すべて網羅）
                area_match = re.search(r'(\d{2,3}(?:\.\d{1,2})?)\s*(?:㎡|平米|m2|m²)', text)
                area = float(area_match.group(1)) if area_match else 0.0

                if price > 0 and area > 0:
                    found_properties.append({
                        "name": name,
                        "ward": ward,
                        "price": price,
                        "previous_price": old_p,
                        "price_drop": drop,
                        "gap_rate": rate,
                        "area": area,
                        "source": source
                    })

    # 2. テキストメール解析（住友ステップ等）
    text_content = item["plain"] or ""
    if text_content:
        sections = re.split(r'[-=]{10,}|【物件', text_content)
        for sec in sections:
            if not any(k in sec for k in ["価格", "万円", "㎡", "m2", "m²"]):
                continue

            ward = next((w for w in TARGET_WARDS if w in sec), None)
            if not ward:
                continue

            name = ""
            name_m = re.search(r'(?:物件名|名称|マンション名)[：:\s]*([^\n\r]+)', sec)
            if name_m:
                name = clean_text(name_m.group(1))
            else:
                lines = [clean_text(l) for l in sec.splitlines() if len(clean_text(l)) >= 3]
                if lines:
                    name = lines[0]

            if not name or len(name) < 3:
                continue

            # 修正②：テキスト側でも new_p を最優先採用（旧価格の誤保存を完全防止）
            old_p, new_p, drop, rate = parse_price_change(sec)
            if new_p:
                price = new_p
            else:
                price = parse_price(sec)

            area_match = re.search(r'(\d{2,3}(?:\.\d{1,2})?)\s*(?:㎡|平米|m2|m²)', sec)
            area = float(area_match.group(1)) if area_match else 0.0

            if price > 0 and area > 0:
                found_properties.append({
                    "name": name,
                    "ward": ward,
                    "price": price,
                    "previous_price": old_p,
                    "price_drop": drop,
                    "gap_rate": rate,
                    "area": area,
                    "source": source
                })

    return found_properties

def parse_and_screen(emails_data):
    stats = {
        "total_detected": 0,
        "excluded_conditions": 0,
        "recommended": 0,
        "by_source": {}
    }
    
    properties_dict = {}
    excluded_list = []

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

            # 実需フィルター
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

            # 名寄せ・重複マージ
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

    print("\n=== 各社メール検知内訳 ===")
    for src, count in stats["by_source"].items():
        print(f"■ {src}: {count}件 検知")
    print(f"===========================")
    print(f"全体更新完了: 提案推奨 {stats['recommended']}件 / 実需除外 {stats['excluded_conditions']}件")

if __name__ == "__main__":
    main()
