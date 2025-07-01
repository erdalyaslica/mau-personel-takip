# Gerekli kütüphaneleri içe aktar
import requests
import csv
import os
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
import logging
import sys
from dotenv import load_dotenv
import time

# --- SABİTLER ---
LOG_FILE = 'MAU_Rehber.log'
PERSISTENT_FILE = "rehber_durumu.csv"
API_URL = "https://rehber.maltepe.edu.tr/rehber/Home/GetPerson"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest"
}
LETTERS = "ABCÇDEFGĞHIİJKLMNOÖPRSŞTUÜVYZ"

def setup_logging():
    """Loglama sistemini ayarlar, hem dosyaya hem konsola yazar."""
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                        handlers=[logging.FileHandler(LOG_FILE, encoding='utf-8'), logging.StreamHandler(sys.stdout)])

def load_config():
    """Ayarları yükler."""
    load_dotenv()
    config = {
        'sender_email': os.getenv('SENDER_EMAIL'), 'password': os.getenv('SENDER_PASSWORD'),
        'receiver_emails': os.getenv('RECEIVER_EMAILS'), 'smtp_server': "smtp.gmail.com", 'smtp_port': 587
    }
    if not all([config['sender_email'], config['password'], config['receiver_emails']]):
        logging.error("Bir veya daha fazla ortam değişkeni ayarlanmamış. Lütfen .env dosyanızı veya GitHub Secrets ayarlarınızı kontrol edin.")
        return None
    return config

def send_failure_email(config, error_details):
    """Programda bir hata oluştuğunda uyarı e-postası gönderir."""
    try:
        sender = config['sender_email']
        password = config['password']
        receivers = [email.strip() for email in config['receiver_emails'].split(',')]
        subject = "❗ Personel Rehberi Takip Betiği Başarısız Oldu"
        body = f"<h2>Personel Rehberi Otomasyonu Hata Bildirimi</h2><p>Merhaba,</p><p>Personel rehberini kontrol eden otomatik betik bir hata nedeniyle çalışmasını tamamlayamadı.</p><p><b>Hata Detayı:</b></p><pre>{error_details}</pre>"
        msg = MIMEText(body, 'html', 'utf-8')
        msg['Subject'] = subject
        msg['From'] = sender
        msg['To'] = ", ".join(receivers)
        logging.info("Hata raporu e-postası gönderiliyor...")
        with smtplib.SMTP(config['smtp_server'], config['smtp_port']) as server:
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, receivers, msg.as_string())
        logging.info("Hata raporu e-postası başarıyla gönderildi.")
    except Exception as e:
        logging.error(f"HATA RAPORU E-POSTASI GÖNDERİLİRKEN YENİ BİR HATA OLUŞTU: {e}")

def send_email_report(config, added, removed, stats):
    """Değişiklikleri ve istatistikleri içeren bir e-posta raporu gönderir."""
    sender = config['sender_email']
    password = config['password']
    receivers_list = [email.strip() for email in config['receiver_emails'].split(',')]
    today_str = datetime.now().strftime("%d %B %Y %H:%M")
    subject = f"Maltepe Üniversitesi Personel Rehberi Değişiklik Raporu - {today_str}"
    body = f"<h2>Personel Rehberi Raporu ({today_str})</h2>"
    body += "<h3>📊 Genel İstatistikler</h3>"
    body += f"<ul><li><b>Toplam Personel Sayısı:</b> {stats['total_count']}</li></ul>"
    if added or removed:
        body += "<h3>🔄 Tespit Edilen Değişiklikler</h3>"
        if added: body += "<h4>✅ Yeni Eklenen Personel</h4><ul>" + "".join([f"<li><b>{p['Ad Soyad']}</b> - {p['Birim']}</li>" for p in added]) + "</ul>"
        if removed: body += "<h4>❌ Listeden Çıkarılan Personel</h4><ul>" + "".join([f"<li><b>{p['Ad Soyad']}</b> - {p['Birim']}</li>" for p in removed]) + "</ul>"
    body += "<hr><p>Bu, otomatik bir bildirimdir.</p>"
    msg = MIMEText(body, 'html', 'utf-8')
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = ", ".join(receivers_list)
    with smtplib.SMTP(config['smtp_server'], config['smtp_port']) as server:
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, receivers_list, msg.as_string())
    logging.info("Değişiklik raporu e-postası gönderildi.")

def extract_data_via_api():
    """Sitenin API'sine doğrudan istek göndererek tüm personeli çeker."""
    all_results = []
    collected_ids = set()

    for letter in LETTERS:
        payload = {"groupId": None, "key": letter, "nameLike": False}
        logging.info(f"API'ye '{letter}' harfi için istek gönderiliyor...")
        try:
            response = requests.post(API_URL, json=payload, headers=HEADERS, timeout=30)
            response.raise_for_status() 
            data = response.json()
            if data.get("Data"):
                letter_results = data["Data"]
                for person in letter_results:
                    ad_soyad = f"{person.get('Adi', '')} {person.get('Soyadi', '')}".strip()
                    birim = person.get('BirimAdi', 'Birim Bilgisi Yok').split('|')[0].strip()
                    person_id = f"{ad_soyad}|{birim}"
                    if person_id not in collected_ids:
                        collected_ids.add(person_id)
                        all_results.append({'Ad Soyad': ad_soyad, 'Birim': birim})
            else:
                logging.warning(f"'{letter}' harfi için veri bulunamadı.")
            time.sleep(0.5)
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"API isteği sırasında bir hata oluştu: {e}")

    logging.info(f"Toplam {len(all_results)} benzersiz personel verisi çekildi.")
    return all_results

def compare_lists(previous_list, current_list):
    get_id = lambda p: f"{p.get('Ad Soyad', '')}|{p.get('Birim', '')}"
    previous_ids = {get_id(p) for p in previous_list}
    current_ids = {get_id(p) for p in current_list}
    
    logging.info(f"Karşılaştırma: Önceki listede {len(previous_ids)} kayıt, güncel listede {len(current_ids)} kayıt var.")
    
    added_ids = current_ids - previous_ids
    removed_ids = previous_ids - current_ids
    
    added = [p for p in current_list if get_id(p) in added_ids]
    removed = [p for p in previous_list if get_id(p) in removed_ids]
    
    return added, removed

def analyze_statistics(personnel_list):
    stats = {}; stats['total_count'] = len(personnel_list)
    return stats

def main():
    setup_logging()
    logging.info("="*30); logging.info("Kontrol başlatıldı (API Modu).")
    config = load_config()
    if not config: sys.exit(1)
    
    try:
        previous_results = []
        # --- YENİ TEŞHİS LOGLARI ---
        logging.info(f"Mevcut çalışma dizini: {os.getcwd()}")
        logging.info(f"Kontrol edilen dosya yolu: {os.path.abspath(PERSISTENT_FILE)}")
        
        if os.path.exists(PERSISTENT_FILE):
            logging.info(f"Önceki personel listesi ({PERSISTENT_FILE}) bulundu. Okunuyor...")
            try:
                with open(PERSISTENT_FILE, "r", newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    previous_results = [row for row in reader if row]
                logging.info(f"Başarıyla {len(previous_results)} kayıt önceki listeden okundu.")
            except Exception as e:
                logging.error(f"Önceki personel listesi okunurken bir hata oluştu: {e}")
        else:
            logging.warning(f"Önceki personel listesi ({PERSISTENT_FILE}) bulunamadı. Bu ilk çalıştırma olabilir.")
            
        current_results = extract_data_via_api()
            
        if not current_results:
            raise RuntimeError("API'den personel listesi çekilemedi (boş liste döndü).")
        
        logging.info("Listeler karşılaştırılıyor...")
        added, removed = compare_lists(previous_results, current_results)
        statistics = analyze_statistics(current_results)
        
        if added or removed:
            logging.info(f"Değişiklikler tespit edildi: {len(added)} yeni, {len(removed)} çıkarılan.")
            send_email_report(config, added, removed, statistics)
        else:
            logging.info("Değişiklik tespit edilmedi. E-posta gönderilmeyecek.")
            
        logging.info(f"Güncel personel durumu dosyaya yazılıyor: {PERSISTENT_FILE}")
        with open(PERSISTENT_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["Ad Soyad", "Birim"])
            writer.writeheader()
            writer.writerows(current_results)
            
        logging.info("İşlem başarıyla tamamlandı.")
        
    except Exception as e:
        logging.exception("Programın çalışması sırasında beklenmedik bir hata oluştu.")
        send_failure_email(config, str(e))
    finally:
        logging.info("Kontrol tamamlandı."); logging.info("="*30 + "\n")

if __name__ == "__main__":
    main()
