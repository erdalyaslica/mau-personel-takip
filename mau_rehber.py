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

# Sabitler
LOG_FILE = 'personel_rehber.log'
PERSISTENT_FILE = "rehber_durumu.csv"
API_URL = "https://rehber.maltepe.edu.tr/rehber/Home/GetPerson"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest"
}
LETTERS = "ABCÇDEFGHIİJKLMNOÖPRSŞTUÜVYZ"

def setup_logging():
    """Loglama sistemini ayarlar"""
    # Eski log handler'larını temizleyerek tekrar tekrar eklenmesini önle
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )

def load_config():
    """Gerekli ayarları yükler"""
    load_dotenv()
    required_vars = ['SENDER_EMAIL', 'SENDER_PASSWORD', 'RECEIVER_EMAILS']
    missing = [var for var in required_vars if not os.getenv(var)]
    
    if missing:
        logging.error(f"Eksik ortam değişkenleri: {', '.join(missing)}")
        return None
        
    return {
        'sender_email': os.getenv('SENDER_EMAIL'),
        'password': os.getenv('SENDER_PASSWORD'),
        'receiver_emails': os.getenv('RECEIVER_EMAILS'),
        'smtp_server': "smtp.gmail.com",
        'smtp_port': 587
    }

def send_email(config, subject, body, is_html=True):
    """E-posta gönderir"""
    try:
        msg = MIMEText(body, 'html' if is_html else 'plain', 'utf-8')
        msg['Subject'] = subject
        msg['From'] = config['sender_email']
        msg['To'] = config['receiver_emails']
        
        with smtplib.SMTP(config['smtp_server'], config['smtp_port']) as server:
            server.starttls()
            server.login(config['sender_email'], config['password'])
            server.sendmail(
                config['sender_email'],
                [email.strip() for email in config['receiver_emails'].split(',')],
                msg.as_string()
            )
        logging.info("E-posta gönderildi")
    except Exception as e:
        logging.error(f"E-posta gönderilemedi: {str(e)}")

def fetch_personnel_data():
    """API'den personel verilerini çeker"""
    personnel = []
    seen_ids = set()

    for letter in LETTERS:
        try:
            response = requests.post(
                API_URL,
                json={"groupId": None, "key": letter, "nameLike": False},
                headers=HEADERS,
                timeout=30
            )
            response.raise_for_status()
            
            for person in response.json().get("Data", []):
                full_name = f"{person.get('Adi', '')} {person.get('Soyadi', '')}".strip()
                department = person.get('BirimAdi', 'Belirsiz').split('|')[0].strip()
                person_id = f"{full_name}|{department}"
                
                if person_id not in seen_ids:
                    seen_ids.add(person_id)
                    personnel.append({'Ad Soyad': full_name, 'Birim': department})
                    
            time.sleep(0.5)
        except Exception as e:
            logging.error(f"'{letter}' harfi için veri çekilemedi: {str(e)}")
    
    logging.info(f"Toplam {len(personnel)} personel kaydı alındı")
    return personnel

def compare_lists(old_list, new_list):
    """İki listeyi karşılaştırır"""
    def get_key(p): return f"{p.get('Ad Soyad', 'None')}|{p.get('Birim', 'None')}"
    
    old_keys = {get_key(p) for p in old_list}
    new_keys = {get_key(p) for p in new_list}
    
    added = [p for p in new_list if get_key(p) not in old_keys]
    removed = [p for p in old_list if get_key(p) not in new_keys]
    
    return added, removed

def generate_report(added, removed, total):
    """Rapor içeriğini oluşturur"""
    date_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    report = f"""
    <h2>Personel Rehberi Raporu ({date_str})</h2>
    <p><b>Toplam Personel:</b> {total}</p>
    """
    
    if added:
        report += "<h3>Yeni Eklenenler</h3><ul>" + \
                  "".join(f"<li>{p['Ad Soyad']} - {p['Birim']}</li>" for p in added) + \
                  "</ul>"
    
    if removed:
        report += "<h3>Çıkarılanlar</h3><ul>" + \
                  "".join(f"<li>{p['Ad Soyad']} - {p['Birim']}</li>" for p in removed) + \
                  "</ul>"
    
    return report

def main():
    setup_logging()
    logging.info("="*50)
    logging.info("Personel rehber kontrolü başlatıldı")
    
    config = load_config()
    if not config:
        sys.exit(1)
    
    try:
        # Önceki verileri yükle
        previous_data = []
        is_first_run = not os.path.exists(PERSISTENT_FILE)
        
        if not is_first_run:
            try:
                with open(PERSISTENT_FILE, 'r', encoding='utf-8') as f:
                    previous_data = list(csv.DictReader(f))
                logging.info(f"Önceki veri yüklendi ({len(previous_data)} kayıt)")
            except Exception as e:
                logging.error(f"Önceki veri yüklenemedi: {str(e)}")
                is_first_run = True # Dosya okunamıyorsa, ilk çalıştırma gibi davran
        else:
            logging.warning("Önceki veri dosyası bulunamadı. Bu ilk çalıştırma olabilir.")

        # Yeni verileri al
        current_data = fetch_personnel_data()
        if not current_data:
            raise RuntimeError("API'den veri alınamadı")
        
        # Karşılaştırma yap
        added, removed = compare_lists(previous_data, current_data)
        
        # --- DÜZELTİLMİŞ MANTIK ---
        # Sadece değişiklik varsa VEYA bu ilk çalıştırma ise e-posta gönder.
        if added or removed or is_first_run:
            subject = "Personel Rehberi Güncellemesi"
            if is_first_run:
                subject += " (İlk Çalıştırma Raporu)"
                # İlk çalıştırmada herkes yeni eklenmiş gibi görünür, bu normaldir.
                # Bu yüzden 'added' listesini güncel liste ile dolduruyoruz.
                added = current_data
                removed = []
            
            report = generate_report(added, removed, len(current_data))
            send_email(config, subject, report)
        else:
            logging.info("Değişiklik yok, e-posta gönderilmedi")
        
        # Yeni veriyi kaydet
        with open(PERSISTENT_FILE, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['Ad Soyad', 'Birim'])
            writer.writeheader()
            writer.writerows(current_data)
        
        logging.info("İşlem başarıyla tamamlandı")
        
    except Exception as e:
        logging.error(f"Kritik hata: {str(e)}", exc_info=True)
        if config:
            send_email(config, "Personel Rehberi Hatası", f"<p>Hata oluştu:</p><pre>{str(e)}</pre>")
        sys.exit(1)
    finally:
        logging.info("="*50)

if __name__ == "__main__":
    main()
