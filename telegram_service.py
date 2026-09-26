"""Persistent Telegram command worker. Run exactly one instance per bot token."""

import csv
import io
import logging
import os
import time
from datetime import datetime

import requests

import mau_rehber
from telegram_bot import compare_states, control_result_text, format_person, normalize_command, parse_csv_line, help_text

REPO = os.getenv("GH_REPOSITORY", "erdalyaslica/mau-personel-takip")
BRANCH = os.getenv("GH_BRANCH", "main")
STATE_PATH = "rehber_durumu.csv"
API = "https://api.github.com/repos/" + REPO
SESSION = requests.Session()


def github(method, path, **kwargs):
    token = os.environ["GH_TOKEN"]
    response = SESSION.request(
        method, API + path,
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json"},
        timeout=45,
        **kwargs,
    )
    response.raise_for_status()
    return response.json()


def read_state():
    import base64

    try:
        file = github("GET", "/contents/" + STATE_PATH, params={"ref": BRANCH})
    except requests.HTTPError as exc:
        if exc.response.status_code == 404:
            return [], None
        raise
    content = base64.b64decode(file["content"]).decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(content))), file["sha"]


def write_state(rows, sha):
    import base64

    output = io.StringIO(newline="")
    fields = ("Unvan", "Ad", "Soyad", "Birim", "Görev", "E-posta", "Dahili")
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    payload = {
        "message": "Personel rehber botu durumunu güncelle",
        "content": base64.b64encode(("\ufeff" + output.getvalue()).encode("utf-8")).decode("ascii"),
        "branch": BRANCH,
    }
    if sha:
        payload["sha"] = sha
    return github("PUT", "/contents/" + STATE_PATH, json=payload)


def recent_text(limit=5):
    commits = github("GET", "/commits", params={"path": STATE_PATH, "sha": BRANCH, "per_page": 40})
    events = []
    for item in commits:
        commit = github("GET", "/commits/" + item["sha"])
        date = datetime.fromisoformat(item["commit"]["committer"]["date"].replace("Z", "+00:00"))
        date = date.astimezone(__import__("zoneinfo").ZoneInfo("Europe/Istanbul")).strftime("%d.%m.%Y %H:%M")
        changed = next((f for f in commit.get("files", []) if f["filename"] == STATE_PATH), None)
        if not changed or not changed.get("patch"):
            continue
        removed, added = {}, {}
        for line in changed["patch"].splitlines():
            if line.startswith(("+++", "---")) or not line.startswith(("+", "-")):
                continue
            person = parse_csv_line(line[1:])
            if not person:
                continue
            key = (person.get("E-posta") or "").strip().casefold() or (
                (person.get("Ad") or "") + " " + (person.get("Soyad") or "")
            ).strip().casefold()
            (added if line.startswith("+") else removed)[key] = person
        for key in dict.fromkeys([*removed, *added]):
            old, new = removed.get(key), added.get(key)
            if old and new:
                if old != new:
                    events.append((date, "🟡 Güncellendi", new))
            elif new:
                events.append((date, "🟢 Yeni", new))
            elif old:
                events.append((date, "🔴 Ayrıldı", old))
            if len(events) == limit:
                break
        if len(events) == limit:
            break
    if not events:
        return "ℹ️ Son personel değişiklikleri Git geçmişinden bulunamadı."
    lines = [f"🕘 Son {len(events)} personel değişikliği"]
    for date, kind, person in events:
        name, unit = format_person(person)
        lines.extend(["", f"{kind} · {date}", f"• {name}", f"  └ {unit}"])
    return "\n".join(lines)


def telegram(token, method, **params):
    response = SESSION.post("https://api.telegram.org/bot" + token + "/" + method, json=params, timeout=55)
    response.raise_for_status()
    result = response.json()
    if not result.get("ok"):
        raise RuntimeError(result.get("description", "Telegram API error"))
    return result["result"]


def send(token, chat, text):
    # Telegram caps text at 4096 characters; split lengthy person lists safely.
    while text:
        part, text = text[:3800], text[3800:]
        telegram(token, "sendMessage", chat_id=chat, text=part)


def control(token, chat):
    send(token, chat, "⏳ Rehber kontrolü başladı. Liste taranıyor; sonuç burada bildirilecek.")
    try:
        old, sha = read_state()
        current = mau_rehber.fetch_personnel()
        # The scheduled workflow may have written a newer snapshot during the scan.
        latest, latest_sha = read_state()
        if latest_sha != sha:
            old, sha = latest, latest_sha
        added, removed = compare_states(old, current)
        if added or removed or not sha:
            write_state(current, sha)
        send(token, chat, control_result_text(old, current))
        if old and (added or removed) and all(os.getenv(key) for key in (
            "SENDER_EMAIL", "SENDER_PASSWORD", "RECEIVER_EMAILS"
        )):
            try:
                mau_rehber.send_email(
                    "Maltepe Rehber Değişiklik Raporu",
                    mau_rehber.report_html(added, removed, len(current)),
                )
            except Exception:
                logging.exception("E-posta gönderilemedi")
                send(token, chat, "⚠️ Rehber kaydedildi, ancak e-posta bildirimi gönderilemedi.")
    except Exception:
        logging.exception("Rehber taraması başarısız")
        send(token, chat, "⚠️ Rehber kontrolü tamamlanamadı. Liste korunuyor; servis kayıtlarına bakın.")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    token = os.environ["TG_TOKEN"].strip()
    chat = os.environ["TG_ALLOWED_CHAT_ID"].strip()
    for key in ("GH_TOKEN", "SCRAPEDO_TOKEN"):
        if not os.getenv(key):
            raise RuntimeError("Eksik ortam değişkeni: " + key)
    offset = None
    while True:
        try:
            updates = telegram(token, "getUpdates", offset=offset, timeout=40, allowed_updates=["message"])
            for update in updates:
                offset = update["update_id"] + 1
                message = update.get("message") or {}
                if str((message.get("chat") or {}).get("id", "")) != chat:
                    continue
                command = normalize_command(message.get("text", ""))
                try:
                    if command == "kontrol":
                        control(token, chat)
                    elif command == "son5":
                        send(token, chat, recent_text())
                    elif command == "yardim":
                        send(token, chat, help_text())
                    elif command == "unknown":
                        send(token, chat, "❓ Komutu anlayamadım.\n\n" + help_text())
                except Exception:
                    logging.exception("Telegram komutu başarısız: %s", command)
                    send(token, chat, "⚠️ Komut tamamlanamadı. Servis kayıtlarına bakın.")
            # Acknowledge processed updates before a restart can cause duplicates.
            if updates:
                telegram(token, "getUpdates", offset=offset, timeout=0, allowed_updates=["message"])
        except Exception:
            logging.exception("Telegram bağlantısı kesildi; yeniden denenecek")
            time.sleep(5)


if __name__ == "__main__":
    main()
