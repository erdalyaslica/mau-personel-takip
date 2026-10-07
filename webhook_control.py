"""Run one requested personnel scan and always report its outcome to Telegram."""

import logging
import signal
import sys

import mau_rehber
from telegram_bot import control_result_text


def _timeout(signum, frame):
    raise TimeoutError("Rehber taraması 12 dakikayı aştı")


def main():
    mau_rehber.setup_logging()
    signal.signal(signal.SIGALRM, _timeout)
    signal.alarm(12 * 60)
    try:
        before = mau_rehber.load_state()
        after = mau_rehber.fetch_personnel()
        added, removed = mau_rehber.compare(before, after)
        mau_rehber.write_result("personel", status="success", summary="Değişiklik yok." if not (added or removed) else f"{len(added)} yeni katılan, {len(removed)} ayrılan.", total=len(after), added=[mau_rehber.person_summary(p) for p in added], removed=[mau_rehber.person_summary(p) for p in removed])
        mau_rehber.save_state(after)

        # /kontrol isteği de her seferinde iki kanala sonuç özeti gönderir.
        # PANEL_ONLY ile başlayan panel kontrollerinde ilgili fonksiyonlar sessiz kalır.
        subject = "Maltepe Rehber Kontrol Sonucu"
        if added or removed:
            subject = "Maltepe Rehber Değişiklik Raporu"
        try:
            mau_rehber.send_email(
                subject,
                mau_rehber.report_html(added, removed, len(after)),
            )
        except Exception:
            logging.exception("E-posta bildirimi başarısız")
        try:
            mau_rehber.send_telegram(control_result_text(before, after))
        except Exception:
            logging.exception("Telegram bildirimi başarısız")
        return 0
    except Exception:
        logging.exception("İstenen rehber taraması tamamlanamadı")
        try:
            mau_rehber.send_telegram("⚠️ Rehber kontrolü veya bildirimi tamamlanamadı. Ayrıntı için Actions kaydını kontrol edin.")
        except Exception:
            logging.exception("Hata mesajı da Telegram'a gönderilemedi")
        return 1
    finally:
        signal.alarm(0)


if __name__ == "__main__":
    sys.exit(main())
