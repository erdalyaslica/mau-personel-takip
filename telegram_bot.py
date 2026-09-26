import csv
import io
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import requests

OFFSET_FILE = Path("telegram_offset.txt")
STATE_FILE = Path("rehber_durumu.csv")
API_BASE = "https://api.telegram.org/bot{}"


def required(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Eksik ortam değişkeni: {name}")
    return value


def telegram_call(token, method, **params):
    response = requests.post(
        API_BASE.format(token) + "/" + method,
        json=params,
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(payload.get("description", f"Telegram {method} başarısız"))
    return payload.get("result")


def send_message(token, chat_id, text):
    try:
        telegram_call(token, "sendMessage", chat_id=chat_id, text=text)
    except Exception:
        logging.exception("Telegram mesajı gönderilemedi")


def read_offset():
    if not OFFSET_FILE.exists():
        return 0
    try:
        return int(OFFSET_FILE.read_text(encoding="utf-8").strip() or "0")
    except ValueError:
        logging.warning("Telegram offset dosyası geçersiz; sıfırdan başlanıyor.")
        return 0


def save_offset(offset):
    temp_file = OFFSET_FILE.with_suffix(".tmp")
    temp_file.write_text(str(offset) + "\n", encoding="utf-8")
    temp_file.replace(OFFSET_FILE)


def normalize_command(text):
    text = " ".join((text or "").strip().casefold().split())
    if not text:
        return ""
    if text.startswith("/"):
        first, *rest = text.split(maxsplit=1)
        first = first.split("@", 1)[0]
        text = first + ((" " + rest[0]) if rest else "")
    aliases = {
        "/kontrol": "kontrol",
        "kontrol": "kontrol",
        "/son5": "son5",
        "/son 5": "son5",
        "son5": "son5",
        "son 5": "son5",
        "/yardım": "yardim",
        "/yardim": "yardim",
        "yardım": "yardim",
        "yardim": "yardim",
        "/help": "yardim",
        "/start": "yardim",
    }
    return aliases.get(text, "unknown")


def help_text():
    return (
        "📚 Maltepe Personel Rehber Botu\n\n"
        "• /kontrol veya kontrol — rehberi şimdi tarar ve sonucu açıkça bildirir\n"
        "• /son5 veya son 5 — son 5 personel değişikliğini gösterir\n"
        "• /yardım — bu mesajı gösterir"
    )


def load_state():
    if not STATE_FILE.exists():
        return []
    with STATE_FILE.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def person_key(person):
    email = (person.get("E-posta") or "").strip().casefold()
    if email:
        return ("mail", email)
    name = ((person.get("Ad") or "") + " " + (person.get("Soyad") or "")).strip().casefold()
    return ("name", name)


def compare_states(old, new):
    old_map = {person_key(p): p for p in old}
    new_map = {person_key(p): p for p in new}
    added = [p for k, p in new_map.items() if k not in old_map]
    removed = [p for k, p in old_map.items() if k not in new_map]
    return added, removed


def run_rehber_kontrol():
    return subprocess.run(
        [sys.executable, str(Path(__file__).with_name("mau_rehber.py"))],
        check=False,
    ).returncode


def format_person(person):
    name = ((person.get("Ad") or "") + " " + (person.get("Soyad") or "")).strip() or "İsim belirtilmemiş"
    unit = (person.get("Birim") or "").strip() or "Birim belirtilmemiş"
    return name, unit


def control_result_text(before, after):
    added, removed = compare_states(before, after)
    lines = [
        "✅ Rehber kontrolü tamamlandı.",
        f"👥 Güncel toplam: {len(after)}",
        f"🟢 Yeni: {len(added)} | 🔴 Ayrılan: {len(removed)}",
    ]
    if not added and not removed:
        lines.append("ℹ️ Önceki kayıtla karşılaştırıldığında personel giriş/çıkışı yok.")
    else:
        if added:
            lines.append("\n🟢 YENİ KATILANLAR")
            for person in added:
                name, unit = format_person(person)
                lines.extend([f"• {name}", f"  └ {unit}"])
        if removed:
            lines.append("\n🔴 AYRILANLAR")
            for person in removed:
                name, unit = format_person(person)
                lines.extend([f"• {name}", f"  └ {unit}"])
    return "\n".join(lines)


def parse_csv_line(line):
    try:
        row = next(csv.reader(io.StringIO(line)))
    except Exception:
        return None
    if len(row) < 7 or row[0] == "Unvan":
        return None
    return {
        "Unvan": row[0],
        "Ad": row[1],
        "Soyad": row[2],
        "Birim": row[3],
        "Görev": row[4],
        "E-posta": row[5],
        "Dahili": row[6],
    }


def recent_changes(limit=5):
    """Git geçmişindeki rehber CSV farklarından son personel değişikliklerini çıkarır."""
    try:
        result = subprocess.run(
            [
                "git", "log", "-n", "40", "--date=format:%d.%m.%Y %H:%M",
                "--pretty=format:@@COMMIT@@%ad", "-p", "--", str(STATE_FILE)
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except Exception:
        logging.exception("Git geçmişi okunamadı")
        return []

    events = []
    current_date = ""
    removed_by_email = {}
    added_by_email = {}

    def flush_commit():
        nonlocal removed_by_email, added_by_email
        emails = list(dict.fromkeys(list(removed_by_email) + list(added_by_email)))
        for email in emails:
            old = removed_by_email.get(email)
            new = added_by_email.get(email)
            if old and new:
                if old != new:
                    events.append((current_date, "🟡 Güncellendi", new))
            elif new:
                events.append((current_date, "🟢 Yeni", new))
            elif old:
                events.append((current_date, "🔴 Ayrıldı", old))
        removed_by_email = {}
        added_by_email = {}

    for raw in result.stdout.splitlines():
        if raw.startswith("@@COMMIT@@"):
            if current_date:
                flush_commit()
                if len(events) >= limit:
                    break
            current_date = raw.replace("@@COMMIT@@", "", 1).strip()
            continue
        if raw.startswith("+++") or raw.startswith("---") or raw.startswith("@@"):
            continue
        if raw.startswith("+") or raw.startswith("-"):
            person = parse_csv_line(raw[1:])
            if not person:
                continue
            email = (person.get("E-posta") or "").strip().casefold()
            key = email or (((person.get("Ad") or "") + " " + (person.get("Soyad") or "")).strip().casefold())
            if raw.startswith("+"):
                added_by_email[key] = person
            else:
                removed_by_email[key] = person
    if current_date and len(events) < limit:
        flush_commit()

    return events[:limit]


def recent_changes_text(limit=5):
    events = recent_changes(limit)
    if not events:
        return "ℹ️ Son personel değişiklikleri Git geçmişinden bulunamadı."
    lines = [f"🕘 Son {len(events)} personel değişikliği"]
    for date_text, kind, person in events:
        name, unit = format_person(person)
        lines.extend(["", f"{kind} · {date_text}", f"• {name}", f"  └ {unit}"])
    return "\n".join(lines)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    token = required("TG_TOKEN")
    allowed_chat_id = required("TG_ALLOWED_CHAT_ID")
    offset = read_offset()

    updates = telegram_call(
        token,
        "getUpdates",
        offset=offset,
        timeout=0,
        allowed_updates=["message"],
    ) or []

    if not updates:
        logging.info("Bekleyen Telegram komutu yok.")
        return 0

    next_offset = max(update["update_id"] for update in updates) + 1
    control_requested = False
    control_chat_id = allowed_chat_id

    for update in updates:
        message = update.get("message") or {}
        chat_id = str((message.get("chat") or {}).get("id", ""))
        if chat_id != allowed_chat_id:
            continue

        command = normalize_command(message.get("text", ""))
        if command == "kontrol":
            control_requested = True
            control_chat_id = chat_id
        elif command == "son5":
            send_message(token, chat_id, recent_changes_text(5))
        elif command == "yardim":
            send_message(token, chat_id, help_text())
        elif command == "unknown":
            send_message(token, chat_id, "❓ Komutu anlayamadım.\n\n" + help_text())

    save_offset(next_offset)

    if not control_requested:
        return 0

    before = load_state()
    send_message(
        token,
        control_chat_id,
        "⏳ Rehber kontrolü başlatıldı. Güncel liste taranıyor; tamamlanınca sonucu burada yazacağım.",
    )

    return_code = run_rehber_kontrol()
    if return_code == 0:
        after = load_state()
        send_message(token, control_chat_id, control_result_text(before, after))
    else:
        send_message(
            token,
            control_chat_id,
            "⚠️ Rehber kontrolü tamamlanamadı. Tarama sırasında hata oluştu; mevcut kayıt dosyası değiştirilmedi.",
        )

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        logging.exception("Telegram komut işleyicisi başarısız")
        sys.exit(1)
