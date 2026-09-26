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
        mau_rehber.save_state(after)
        mau_rehber.send_telegram(control_result_text(before, after))
        if before and (added or removed):
            try:
                mau_rehber.send_email(
                    "Maltepe Rehber Değişiklik Raporu",
                    mau_rehber.report_html(added, removed, len(after)),
                )
            except Exception:
                logging.exception("E-posta bildirimi başarısız")
                mau_rehber.send_telegram("⚠️ Rehber kaydedildi, ancak e-posta bildirimi gönderilemedi.")
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
