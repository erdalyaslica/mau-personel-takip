import logging
import os
import subprocess
import sys
from pathlib import Path

import requests

OFFSET_FILE = Path("telegram_offset.txt")
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


def command_name(text):
    first_word = (text or "").strip().split(maxsplit=1)
    if not first_word:
        return ""
    return first_word[0].split("@", 1)[0].casefold()


def help_text():
    return (
        "Maltepe Personel Rehber Botu\n\n"
        "/kontrol — rehberi şimdi kontrol eder\n"
        "/yardım — bu yardım mesajını gösterir"
    )


def run_rehber_kontrol():
    return subprocess.run(
        [sys.executable, str(Path(__file__).with_name("mau_rehber.py"))],
        check=False,
    ).returncode


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

        command = command_name(message.get("text", ""))
        if command == "/kontrol":
            control_requested = True
            control_chat_id = chat_id
        elif command in {"/yardım", "/yardim", "/help", "/start"}:
            send_message(token, chat_id, help_text())
        elif command:
            send_message(
                token,
                chat_id,
                "Bilinmeyen komut. Kullanılabilir komutlar:\n/kontrol\n/yardım",
            )

    # İlerleme bilgisi yerel olarak hemen kaydedilir; workflow sonunda GitHub'a commit edilir.
    save_offset(next_offset)

    if not control_requested:
        return 0

    send_message(
        token,
        control_chat_id,
        "⏳ Rehber kontrolü başlatıldı. Tarama tamamlanınca sonucu bildireceğim.",
    )

    return_code = run_rehber_kontrol()
    if return_code == 0:
        send_message(
            token,
            control_chat_id,
            "✅ Rehber kontrolü tamamlandı. Değişiklik varsa ayrıntılı Telegram bildirimi gönderildi.",
        )
    else:
        send_message(
            token,
            control_chat_id,
            "⚠️ Rehber kontrolü tamamlanamadı. Hata bildirimi gönderildiyse ayrıntıları orada görebilirsin.",
        )

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        logging.exception("Telegram komut işleyicisi başarısız")
        sys.exit(1)
