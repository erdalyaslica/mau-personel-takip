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


def email_shell(eyebrow, title, subtitle, content, accent="#0071e3"):
    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#f5f5f7;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;color:#1d1d1f;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f5f5f7;">
<tr><td align="center" style="padding:40px 16px;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:720px;background:#ffffff;border-radius:24px;overflow:hidden;box-shadow:0 8px 32px rgba(0,0,0,.08);">
<tr><td style="height:6px;background:{accent};font-size:0;">&nbsp;</td></tr>
<tr><td style="padding:44px 44px 26px;">
<div style="font-size:12px;line-height:18px;font-weight:700;letter-spacing:1.4px;text-transform:uppercase;color:{accent};">{eyebrow}</div>
<h1 style="margin:10px 0 12px;font-size:34px;line-height:40px;letter-spacing:-.7px;font-weight:700;color:#1d1d1f;">{title}</h1>
<p style="margin:0;font-size:17px;line-height:26px;color:#6e6e73;">{subtitle}</p>
</td></tr>
<tr><td style="padding:0 44px 44px;">{content}</td></tr>
</table>
<p style="margin:20px 0 0;font-size:12px;line-height:18px;color:#86868b;">Maltepe Personel Takip · GitHub Actions</p>
</td></tr></table></body></html>"""


def report_html(added, removed, total):
    def table(title, color, tint, rows):
        if not rows:
            return ""
        body = "".join(
            f"""<tr>
            <td style="padding:15px 12px;border-bottom:1px solid #e8e8ed;font-size:14px;line-height:20px;font-weight:600;color:#1d1d1f;">{html.escape((p['Ad']+' '+p['Soyad']).strip())}</td>
            <td style="padding:15px 12px;border-bottom:1px solid #e8e8ed;font-size:13px;line-height:19px;color:#515154;">{html.escape(p['Birim'])}</td>
            <td style="padding:15px 12px;border-bottom:1px solid #e8e8ed;font-size:13px;line-height:19px;color:#515154;">{html.escape(p['Görev'])}</td>
            </tr>"""
            for p in rows
        )
        return f"""<div style="margin-top:28px;">
        <div style="display:inline-block;padding:7px 12px;border-radius:999px;background:{tint};color:{color};font-size:13px;font-weight:700;">{title} · {len(rows)}</div>
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-top:12px;border:1px solid #e8e8ed;border-radius:16px;border-collapse:separate;border-spacing:0;overflow:hidden;">
        <tr style="background:#f5f5f7;"><th style="padding:12px;text-align:left;font-size:11px;letter-spacing:.5px;color:#6e6e73;">AD SOYAD</th><th style="padding:12px;text-align:left;font-size:11px;letter-spacing:.5px;color:#6e6e73;">BİRİM</th><th style="padding:12px;text-align:left;font-size:11px;letter-spacing:.5px;color:#6e6e73;">GÖREV</th></tr>
        {body}</table></div>"""

    summary = f"""<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin:8px 0 4px;">
    <tr>
      <td width="33%" style="padding:16px 8px 16px 0;"><div style="padding:18px;border-radius:16px;background:#f5f5f7;"><div style="font-size:28px;font-weight:700;">{total}</div><div style="font-size:12px;color:#6e6e73;">Toplam personel</div></div></td>
      <td width="33%" style="padding:16px 4px;"><div style="padding:18px;border-radius:16px;background:#edfaF1;"><div style="font-size:28px;font-weight:700;color:#188038;">+{len(added)}</div><div style="font-size:12px;color:#52755d;">Yeni katılan</div></div></td>
      <td width="33%" style="padding:16px 0 16px 8px;"><div style="padding:18px;border-radius:16px;background:#fff1f0;"><div style="font-size:28px;font-weight:700;color:#d93025;">−{len(removed)}</div><div style="font-size:12px;color:#8f5a56;">Ayrılan</div></div></td>
    </tr></table>"""
    content = summary + table("Yeni katılanlar", "#188038", "#eaf7ee", added) + table("Ayrılanlar", "#d93025", "#fff0ef", removed)
    return email_shell(
        "Personel Rehberi",
        "Rehberde değişiklik var.",
        f"{datetime.now().strftime('%d.%m.%Y %H:%M')} itibarıyla güncel karşılaştırma özeti.",
        content,
    )


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
    chunks, current = [], ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > 3800 and current:
            chunks.append(current.rstrip())
            current = ""
        current += line
    if current:
        chunks.append(current.rstrip())
    for chunk in chunks:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": chunk},
            timeout=30,
        )
        response.raise_for_status()


def telegram_report(added, removed, total):
    lines = [
        "📋 Maltepe Rehber Güncellemesi",
        datetime.now().strftime("🕒 %d.%m.%Y %H:%M"),
        "",
        f"🟢 Yeni: {len(added)}  |  🔴 Ayrılan: {len(removed)}  |  👥 Toplam: {total}",
    ]

    if added:
        lines.extend(["", f"🟢 YENİ KATILANLAR ({len(added)})"])
        for person in added:
            name = (person["Ad"] + " " + person["Soyad"]).strip() or "İsim belirtilmemiş"
            department = person["Birim"] or "Birim belirtilmemiş"
            lines.extend([f"• {name}", f"  └ {department}"])

    if removed:
        lines.extend(["", f"🔴 AYRILANLAR ({len(removed)})"])
        for person in removed:
            name = (person["Ad"] + " " + person["Soyad"]).strip() or "İsim belirtilmemiş"
            department = person["Birim"] or "Birim belirtilmemiş"
            lines.extend([f"• {name}", f"  └ {department}"])

    return "\n".join(lines)


def main():
    setup_logging()
    try:
        if os.getenv("SEND_TEST_EMAIL", "").strip().lower() == "true":
            send_email(
                "Maltepe Rehber Botu Testi Başarılı",
                email_shell(
                    "Sistem Kontrolü",
                    "Her şey hazır.",
                    "GitHub Actions ve e-posta bağlantınız sorunsuz çalışıyor.",
                    f"""<div style="margin-top:28px;padding:22px;border-radius:18px;background:#f5f5f7;">
                    <div style="font-size:14px;font-weight:600;color:#1d1d1f;">Test başarıyla tamamlandı</div>
                    <div style="margin-top:7px;font-size:13px;line-height:20px;color:#6e6e73;">{datetime.now().strftime('%d.%m.%Y %H:%M')} · Personel listesi değiştirilmedi · Scrape.do kredisi kullanılmadı</div>
                    </div>""",
                    "#30a14e",
                ),
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
            send_telegram(telegram_report(added, removed, len(current)))
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
