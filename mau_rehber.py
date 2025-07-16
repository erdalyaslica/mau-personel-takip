import csv
import os
import smtplib
import sys
import time
import logging
from datetime import datetime
from email.mime.text import MIMEText
from dotenv import load_dotenv

# Selenium ve Undetected Chromedriver için gerekli kütüphaneler
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- SABİTLER ---
LOG_FILE = 'personel_rehber.log'
PERSISTENT_FILE = "rehber_durumu.csv"
TARGET_URL = "https://rehber.maltepe.edu.tr/"
LETTERS = "ABCÇDEFGHIİJKLMNOÖPRSŞTUÜVYZ"


def setup_logging():
    """Loglama sistemini ayarlar."""
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
    """Gerekli ortam değişkenlerini yükler."""
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
    """E-posta gönderir."""
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
        logging.info("E-posta başarıyla gönderildi.")
    except Exception as e:
        logging.error(f"E-posta gönderimi sırasında bir hata oluştu: {str(e)}")

def fetch_personnel_data_with_selenium():
    """Selenium kullanarak web sitesinden personel verilerini çeker."""
    personnel = []
    seen_ids = set()

    options = uc.ChromeOptions()
    options.add_argument('--headless')  # Tarayıcıyı arayüz olmadan çalıştırır
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    
    # GitHub Actions ortamında çalışmak için özel ayarlar
    if 'GITHUB_ACTIONS' in os.environ:
        logging.info("GitHub Actions ortamı algılandı. Headless modda çalışılıyor.")
    else:
        logging.info("Lokal ortamda çalışılıyor.")
        # Lokal'de headless olmadan da test edebilirsiniz.
        # options.headless = False 
        
    driver = uc.Chrome(options=options, use_subprocess=False)
    logging.info("Chrome sürücüsü başlatıldı.")
    
    try:
        driver.get(TARGET_URL)
        logging.info(f"Ana sayfa ({TARGET_URL}) açıldı.")

        # Sayfanın yüklenmesini ve arama kutusunun görünür olmasını bekle
        search_box = WebDriverWait(driver, 20).until(
            EC.visibility_of_element_located((By.ID, "personel-adi"))
        )
        
        for letter in LETTERS:
            try:
                logging.info(f"'{letter}' harfi için arama yapılıyor...")
                search_box.clear()
                search_box.send_keys(letter)

                # Arama butonuna tıkla
                driver.find_element(By.ID, "search-button").click()

                # Sonuçların yüklenmesini bekle (spinner kaybolana kadar)
                WebDriverWait(driver, 20).until(
                    EC.invisibility_of_element_located((By.CLASS_NAME, "spinner-border"))
                )

                # Sonuç kartlarını bul
                cards = driver.find_elements(By.CLASS_NAME, "card-body")
                
                for card in cards:
                    try:
                        full_name = card.find_element(By.CLASS_NAME, "card-title").text.strip()
                        department = card.find_element(By.CLASS_NAME, "card-text").text.split('|')[0].strip()
                        
                        person_id = f"{full_name}|{department}"
                        if person_id not in seen_ids:
                            seen_ids.add(person_id)
                            personnel.append({'Ad Soyad': full_name, 'Birim': department})
                    except Exception:
                        # Bazen boş kartlar olabilir, onları atla
                        continue
                
                logging.info(f"'{letter}' harfi için {len(cards)} sonuç işlendi.")
                time.sleep(0.5) # Sunucuyu yormamak için küçük bir bekleme

            except Exception as e:
                logging.error(f"'{letter}' harfi işlenirken bir hata oluştu: {str(e)}")
                continue # Bir harfte hata olursa diğerine geç
    
    finally:
        driver.quit()
        logging.info("Chrome sürücüsü kapatıldı.")

    logging.info(f"Toplam {len(personnel)} benzersiz personel kaydı alındı.")
    return personnel


def compare_lists(old_list, new_list):
    """İki listeyi karşılaştırarak eklenen ve çıkarılanları bulur."""
    def get_key(p): return f"{p.get('Ad Soyad', 'None')}|{p.get('Birim', 'None')}"
    
    old_keys = {get_key(p) for p in old_list}
    new_keys = {get_key(p) for p in new_list}
    
    added = [p for p in new_list if get_key(p) not in old_keys]
    removed = [p for p in old_list if get_key(p) not in new_keys]
    
    return added, removed

def generate_report(added, removed, total):
    """HTML formatında rapor oluşturur."""
    date_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    report = f"""
    <h2>Personel Rehberi Raporu ({date_str})</h2>
    <p><b>Toplam Personel Sayısı:</b> {total}</p>
    """
    
    if added:
        report += "<h3>Yeni Eklenen Personeller</h3><ul>" + \
                  "".join(f"<li>{p['Ad Soyad']} - {p['Birim']}</li>" for p in added) + \
                  "</ul>"
    
    if removed:
        report += "<h3>Ayrılan Personeller</h3><ul>" + \
                  "".join(f"<li>{p['Ad Soyad']} - {p['Birim']}</li>" for p in removed) + \
                  "</ul>"

    if not added and not removed:
        report += "<p>Herhangi bir değişiklik tespit edilmedi.</p>"
        
    return report

def main():
    setup_logging()
    logging.info("="*50)
    logging.info("Selenium tabanlı personel rehber kontrolü başlatıldı.")
    
    config = load_config()
    if not config:
        sys.exit(1)
    
    try:
        previous_data = []
        is_first_run = not os.path.exists(PERSISTENT_FILE)
        
        if not is_first_run:
            try:
                with open(PERSISTENT_FILE, 'r', encoding='utf-8') as f:
                    previous_data = list(csv.DictReader(f))
                logging.info(f"Önceki veri başarıyla yüklendi ({len(previous_data)} kayıt).")
            except Exception as e:
                logging.warning(f"Önceki veri dosyası okunamadı: {str(e)}. İlk çalıştırma olarak devam edilecek.")
                is_first_run = True
        else:
            logging.warning("Önceki veri dosyası bulunamadı. Bu bir ilk çalıştırma.")

        current_data = fetch_personnel_data_with_selenium()
        if not current_data:
            # Bu sefer hata fırlatmak yerine, veri alınamadığını bildiren bir e-posta gönderelim.
            logging.error("Selenium ile veri çekme işlemi başarısız oldu, hiç kayıt alınamadı.")
            send_email(config, "Personel Rehberi Hatası", "<p>Kritik hata: Web sitesinden hiçbir personel verisi çekilemedi.</p>")
            sys.exit(1)
        
        added, removed = compare_lists(previous_data, current_data)
        
        if added or removed or is_first_run:
            subject = "Personel Rehberi Güncellemesi"
            if is_first_run:
                subject += " (İlk Çalıştırma Raporu)"
                added = current_data
                removed = [] # İlk çalıştırmada ayrılan olmaz.
            
            report = generate_report(added, removed, len(current_data))
            send_email(config, subject, report)
        else:
            logging.info("Rehberde herhangi bir değişiklik yok, e-posta gönderilmedi.")
        
        with open(PERSISTENT_FILE, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['Ad Soyad', 'Birim'])
            writer.writeheader()
            writer.writerows(current_data)
        
        logging.info(f"Yeni veriler '{PERSISTENT_FILE}' dosyasına başarıyla kaydedildi.")
        
    except Exception as e:
        logging.critical(f"Ana işlem bloğunda beklenmedik bir hata oluştu: {str(e)}", exc_info=True)
        send_email(config, "Personel Rehberi Kritik Hatası", f"<h3>Betiğin çalışması sırasında beklenmedik bir hata oluştu:</h3><pre>{str(e)}</pre>")
        sys.exit(1)
    finally:
        logging.info("İşlem tamamlandı.")
        logging.info("="*50)

if __name__ == "__main__":
    main()
