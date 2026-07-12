import csv
import html
import json
import logging
import os
import smtplib
import sys
import time
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path

import requests

API_URL = "https://rehber.maltepe.edu.tr/rehber/Home/GetPerson"
STATE_FILE = Path(os.getenv("STATE_FILE", "rehber_durumu.csv"))
VOWELS = ("a", "e", "i", "u", "ı", "ü")
MIN_PERSONNEL = int(os.getenv("MIN_PERSONNEL", "50"))


def setup_logging():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def required(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Eksik ortam değişkeni: {name}")
    return value


def fetch_one(session, token, letter, premium=False):
    params = {"token": token, "url": API_URL}
    if premium:
        params.update(super="true", geoCode="tr")
    response = session.post(
        "https://api.scrape.do/",
        params=params,
        json={"groupId": None, "key": letter, "nameLike": True},
        timeout=90,
    )
    response.raise_for_status()
    payload = response.json()
    data = payload.get("Data", payload) if isinstance(payload, dict) else payload
    if not isinstance(data, list):
        raise ValueError(f"'{letter}' sorgusu beklenen listeyi döndürmedi")
    return data


def fetch_personnel():
    token = required("SCRAPEDO_TOKEN")
    results = {}
    pending = list(VOWELS)
    with requests.Session() as session:
        for premium in (False, False, True, True):
            if not pending:
                break
            failed = []
            for letter in pending:
                try:
                    results[letter] = fetch_one(session, token, letter, premium)
                    logging.info("'%s': %d kayıt", letter, len(results[letter]))
                except Exception as exc:
                    logging.warning("'%s' alınamadı (%s): %s", letter, "premium" if premium else "standart", exc)
                    failed.append(letter)
            pending = failed
            if pending:
                time.sleep(2)
    if pending:
        raise RuntimeError("Eksik tarama; durum dosyası korunuyor. Harfler: " + ", ".join(pending))

    unique = {}
    for letter in VOWELS:
        for person in results[letter]:
            key = "|".join(
                [
                    str(person.get("Adi", "")).replace(" ", "").upper(),
                    str(person.get("Soyadi", "")).replace(" ", "").upper(),
                    str(person.get("Mail", "")).strip().casefold(),
                    str(person.get("BirimAdi", "")).strip().casefold(),
                ]
            )
            unique.setdefault(key, normalize(person))
    personnel = list(unique.values())
    if len(personnel) < MIN_PERSONNEL:
        raise RuntimeError(f"Yalnızca {len(personnel)} kişi geldi; durum dosyası güvenlik için korunuyor")
    return personnel


def normalize(p):
    return {
        "Unvan": str(p.get("Unvan", "") or "").strip(),
        "Ad": str(p.get("Adi", p.get("Ad", "")) or "").strip(),
        "Soyad": str(p.get("Soyadi", p.get("Soyad", "")) or "").strip(),
        "Birim": str(p.get("BirimAdi", p.get("Birim", "")) or "").strip(),
        "Görev": str(p.get("GorevAdi", p.get("Görev", "")) or "").strip(),
        "E-posta": str(p.get("Mail", p.get("E-posta", "")) or "").strip(),
        "Dahili": str(p.get("Dahili", "") or "").strip(),
    }


def person_key(p):
    email = p["E-posta"].casefold()
    return ("mail", email) if email else ("name", (p["Ad"] + " " + p["Soyad"]).strip().casefold())


def load_state():
    if not STATE_FILE.exists():
        return []
    with STATE_FILE.open(encoding="utf-8-sig", newline="") as handle:
        return [normalize(row) for row in csv.DictReader(handle)]


def save_state(rows):
    fields = ("Unvan", "Ad", "Soyad", "Birim", "Görev", "E-posta", "Dahili")
    temp = STATE_FILE.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(STATE_FILE)


def compare(old, new):
    old_map = {person_key(p): p for p in old}
    new_map = {person_key(p): p for p in new}
    return [p for k, p in new_map.items() if k not in old_map], [p for k, p in old_map.items() if k not in new_map]


def report_html(added, removed, total):
    def table(title, color, rows):
        if not rows:
            return ""
        body = "".join(
            f"<tr><td>{html.escape((p['Ad']+' '+p['Soyad']).strip())}</td><td>{html.escape(p['Birim'])}</td><td>{html.escape(p['Görev'])}</td></tr>"
            for p in rows
        )
        return f"<h3 style='color:{color}'>{title} ({len(rows)})</h3><table style='width:100%;border-collapse:collapse'><tr><th>Ad Soyad</th><th>Birim</th><th>Görev</th></tr>{body}</table>"
    return f"""<div style='max-width:760px;margin:auto;font-family:Arial;color:#263238'>
    <h2 style='color:#b23b2a'>Maltepe Üniversitesi Personel Rehberi</h2>
    <p>{datetime.now().strftime('%d.%m.%Y %H:%M')} itibarıyla toplam <b>{total}</b> personel.</p>
    {table('Yeni katılanlar', '#16803c', added)}{table('Ayrılanlar', '#b42318', removed)}
    </div>"""


def send_email(subject, body):
    sender = required("SENDER_EMAIL")
    password = required("SENDER_PASSWORD")
    recipients = [x.strip() for x in required("RECEIVER_EMAILS").split(",") if x.strip()]
    msg = MIMEText(body, "html", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = subject, sender, ", ".join(recipients)
    with smtplib.SMTP(os.getenv("SMTP_SERVER", "smtp.gmail.com"), int(os.getenv("SMTP_PORT", "587"))) as server:
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, recipients, msg.as_string())


def send_telegram(text):
    token, chat_id = os.getenv("TG_TOKEN", "").strip(), os.getenv("TG_ALLOWED_CHAT_ID", "").strip()
    if not token or not chat_id:
        return
    response = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=30)
    response.raise_for_status()


def main():
    setup_logging()
    try:
        if os.getenv("SEND_TEST_EMAIL", "").strip().lower() == "true":
            send_email(
                "Maltepe Rehber Botu Testi Başarılı",
                "<div style='font-family:Arial;max-width:680px;margin:auto'>"
                "<h2 style='color:#16803c'>Test başarılı</h2>"
                "<p>GitHub Actions, e-posta ayarlarınız ve Gmail uygulama şifreniz düzgün çalışıyor.</p>"
                f"<p><b>Test zamanı:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}</p>"
                "<p>Bu test personel listesini değiştirmedi ve Scrape.do kredisi kullanmadı.</p>"
                "</div>",
            )
            logging.info("Test e-postası gönderildi; rehber taraması yapılmadı.")
            return 0
        old = load_state()
        current = fetch_personnel()
        if not old:
            save_state(current)
            logging.info("İlk çalışma: %d kişi başlangıç verisi olarak kaydedildi; bildirim gönderilmedi.", len(current))
            return 0
        added, removed = compare(old, current)
        if added or removed:
            send_email("Maltepe Rehber Değişiklik Raporu", report_html(added, removed, len(current)))
            send_telegram(f"Maltepe Rehber Güncellemesi\nYeni: {len(added)} | Ayrılan: {len(removed)} | Toplam: {len(current)}")
        else:
            logging.info("Değişiklik yok; bildirim gönderilmedi.")
        save_state(current)
        return 0
    except Exception as exc:
        logging.exception("Çalışma başarısız: %s", exc)
        try:
            send_telegram("Maltepe Rehber botu hata verdi: " + str(exc))
        except Exception:
            logging.exception("Telegram hata bildirimi de gönderilemedi")
        return 1


if __name__ == "__main__":
    sys.exit(main())
