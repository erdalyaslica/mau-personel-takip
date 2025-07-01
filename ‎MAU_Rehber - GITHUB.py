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
    """Loglama sistemini ayarlar"""
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
    config = {
        'sender_email': os.getenv('SENDER_EMAIL'),
        'password': os.getenv('SENDER_PASSWORD'),
        'receiver_emails': os.getenv('RECEIVER_EMAILS'),
        'smtp_server': "smtp.gmail.com",
        'smtp_port': 587
    }
    
    if not all(config.values()):
        logging.error("Eksik ortam değişkenleri! Lütfen .env veya GitHub Secrets ayarlarını kontrol edin.")
        return None
    return config

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
        logging.info("E-posta başarıyla gönderildi")
    except Exception as e:
        logging.error(f"E-posta gönderilemedi: {str(e)}")

def fetch_personnel_data():
    """API'den personel verilerini çeker"""
    all_personnel = []
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
            data = response.json().get("Data", [])
            
            for person in data:
                full_name = f"{person.get('Adi', '')} {person.get('Soyadi', '')}".strip()
                department = person.get('BirimAdi', 'Belirsiz').split('|')[0].strip()
                person_id = f"{full_name}|{department}"
                
                if person_id not in seen_ids:
                    seen_ids.add(person_id)
                    all_personnel.append({
                        'Ad Soyad': full_name,
                        'Birim': department
                    })
            time.sleep(0.5)
        except Exception as e:
            logging.error(f"'{letter}' harfi için veri çekilemedi: {str(e)}")
    
    logging.info(f"Toplam {len(all_personnel)} personel kaydı alındı")
    return all_personnel

def compare_personnel_lists(old_list, new_list):
    """İki personel listesini karşılaştırır"""
    def get_key(person):
        return f"{person['Ad Soyad']}|{person['Birim']}"
    
    old_keys = {get_key(p) for p in old_list}
    new_keys = {get_key(p) for p in new_list}
    
    added = [p for p in new_list if get_key(p) not in old_keys]
    removed = [p for p in old_list if get_key(p) not in new_keys]
    
    return added, removed

def generate_report_content(added, removed, total_count):
    """E-posta içeriğini oluşturur"""
    report_date = datetime.now().strftime("%d %B %Y %H:%M")
    content = f"""
    <h2>Personel Rehberi Güncellemesi ({report_date})</h2>
    <p><strong>Toplam Personel Sayısı:</strong> {total_count}</p>
    """
    
    if added:
        content += "<h3>Yeni Eklenenler</h3><ul>"
        content += "".join(f"<li>{p['Ad Soyad']} - {p['Birim']}</li>" for p in added)
        content += "</ul>"
    
    if removed:
        content += "<h3>Çıkarılanlar</h3><ul>"
        content += "".join(f"<li>{p['Ad Soyad']} - {p['Birim']}</li>" for p in removed)
        content += "</ul>"
    
    if not added and not removed:
        content += "<p>Değişiklik tespit edilmedi.</p>"
    
    return content

def main():
    setup_logging()
    logging.info("="*50)
    logging.info("Personel rehberi kontrolü başlatıldı")
    
    config = load_config()
    if not config:
        sys.exit(1)
    
    try:
        # Önceki verileri yükle
        previous_data = []
        cache_hit = os.getenv('CACHE_HIT', 'false').lower() == 'true'
        
        if cache_hit and os.path.exists(PERSISTENT_FILE):
            try:
                with open(PERSISTENT_FILE, mode='r', encoding='utf-8') as f:
                    previous_data = list(csv.DictReader(f))
                logging.info(f"Önceki veri yüklendi ({len(previous_data)} kayıt)")
            except Exception as e:
                logging.error(f"Önceki veri yüklenemedi: {str(e)}")
        
        # Yeni verileri al
        current_data = fetch_personnel_data()
        if not current_data:
            raise RuntimeError("API'den veri alınamadı")
        
        # Karşılaştırma yap
        added, removed = compare_personnel_lists(previous_data, current_data)
        
        # Rapor oluştur
        report_content = generate_report_content(added, removed, len(current_data))
        
        # E-posta gönderim mantığı
        if added or removed or not cache_hit:
            subject = "Personel Rehberi Güncellemesi"
            if not cache_hit:
                subject += " (İlk Çalıştırma)"
                report_content = "<h2>İlk Çalıştırma - Tüm Personel Listesi</h2>" + report_content
            
            send_email(config, subject, report_content)
        else:
            logging.info("Değişiklik yok, e-posta gönderilmedi")
        
        # Yeni veriyi kaydet
        with open(PERSISTENT_FILE, mode='w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['Ad Soyad', 'Birim'])
            writer.writeheader()
            writer.writerows(current_data)
        
        logging.info("İşlem başarıyla tamamlandı")
        
    except Exception as e:
        logging.error(f"Kritik hata: {str(e)}")
        if config:
            send_email(config, "Personel Rehberi Hatası", f"<p>Hata oluştu:</p><pre>{str(e)}</pre>")
        sys.exit(1)
    finally:
        logging.info("="*50)

if __name__ == "__main__":
    main()
