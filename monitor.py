"""
태응약품 재고 모니터링 - GitHub Actions용
drugs.json에서 약품 목록 읽어서 재고 확인 후 이메일 발송
"""

import os
import json
import smtplib
import requests
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# GitHub Secrets에서 환경변수로 받아옴
GMAIL_SENDER       = os.environ.get("GMAIL_SENDER", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
NOTIFY_EMAIL       = os.environ.get("NOTIFY_EMAIL", "")

SITE_ID   = "pds"
SITE_PW   = "5785"
LOGIN_URL  = "https://www.taeeung.com/homepage/Login/Login/Login.asp"
ORDER_URL  = "https://www.taeeung.com/homepage/Order/Order/Order.asp"

# 이전 알림 기록 파일 (Actions 캐시로 유지)
NOTIFIED_FILE = "notified.json"


def load_drugs():
    """drugs.json에서 약품 목록 읽기"""
    try:
        with open("drugs.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            return [d["name"] for d in data.get("drugs", [])]
    except Exception as e:
        print(f"drugs.json 읽기 실패: {e}")
        return []


def load_notified():
    """이전에 알림 보낸 약품 목록 읽기"""
    try:
        with open(NOTIFIED_FILE, "r") as f:
            return set(json.load(f))
    except:
        return set()


def save_notified(notified_set):
    """알림 보낸 약품 목록 저장"""
    with open(NOTIFIED_FILE, "w") as f:
        json.dump(list(notified_set), f)


def send_email(subject, body):
    try:
        msg = MIMEMultipart()
        msg["From"]    = GMAIL_SENDER
        msg["To"]      = NOTIFY_EMAIL
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_SENDER, NOTIFY_EMAIL, msg.as_string())
        print(f"  ✅ 이메일 발송 → {NOTIFY_EMAIL}")
    except Exception as e:
        print(f"  ❌ 이메일 발송 실패: {e}")


def create_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    })
    session.get(LOGIN_URL)
    resp = session.post(LOGIN_URL, data={"id": SITE_ID, "pwd": SITE_PW})
    resp.raise_for_status()
    print("  ✅ 로그인 완료")
    return session


def check_stock(session, drug_name):
    """특정 약품 재고 확인. [(제품명, 재고)] 반환"""
    params = {"goodsnm": drug_name, "goodstp": "", "ordertp": "", "makernm": "", "dealernm": ""}
    resp = session.get(ORDER_URL, params=params, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-kr"

    soup = BeautifulSoup(resp.text, "html.parser")
    rows = soup.select("table.tbl_list tbody tr.ln_physic")

    results = []
    for row in rows:
        cells = row.find_all("td")
        if len(cells) >= 7:
            product_name = cells[2].get_text(strip=True)
            stock_text   = cells[6].get_text(strip=True).replace(",", "")
            try:
                stock = int(stock_text)
            except ValueError:
                stock = 0
            results.append((product_name, stock))
    return results


def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"=== 재고 확인 시작: {now} ===")

    drug_names = load_drugs()
    if not drug_names:
        print("모니터링할 약품이 없습니다. 웹앱에서 약품을 추가해주세요.")
        return

    print(f"모니터링 약품: {', '.join(drug_names)}")

    notified = load_notified()
    session  = create_session()
    updated  = False

    for drug in drug_names:
        print(f"\n[{drug}] 확인 중...")
        try:
            items = check_stock(session, drug)
            if not items:
                print(f"  검색 결과 없음")
                continue

            for product_name, stock in items:
                key = f"{drug}::{product_name}"
                print(f"  {product_name} → 재고: {stock}")

                if stock > 0 and key not in notified:
                    subject = f"[재고알림] {product_name} 입고!"
                    body = (
                        f"안녕하세요!\n\n"
                        f"찾으시던 약품이 입고되었습니다.\n\n"
                        f"  약품명  : {product_name}\n"
                        f"  재고수량: {stock}\n"
                        f"  확인시각: {now}\n\n"
                        f"지금 바로 주문하세요!\n"
                        f"https://www.taeeung.com\n"
                    )
                    send_email(subject, body)
                    notified.add(key)
                    updated = True

                elif stock == 0 and key in notified:
                    # 재고 소진 → 다음 입고 시 다시 알림받도록 초기화
                    notified.discard(key)
                    updated = True

        except Exception as e:
            print(f"  ⚠️ 오류: {e}")

    if updated:
        save_notified(notified)

    print(f"\n=== 확인 완료 ===")


if __name__ == "__main__":
    main()
