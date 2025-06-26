# Gerekli kütüphaneleri içe aktar
import undetected_chromedriver as uc
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import csv
import os
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
from collections import Counter
import logging
import sys
from dotenv import load_dotenv
import time

# --- SABİTLER ---
LOG_FILE = 'MAU_Rehber.log'
PERSISTENT_FILE = "rehber_durumu.csv"
ERROR_SCREENSHOT_FILE = 'error_screenshot.png'
ERROR_HTML_FILE = 'error_page_source.html'

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
        body = f"""
        <h2>Personel Rehberi Otomasyonu Hata Bildirimi</h2><p>Merhaba,</p>
        <p>Personel rehberini kontrol eden otomatik betik bir hata nedeniyle çalışmasını tamamlayamadı.</p>
        <p><b>Hata Detayı:</b></p><pre>{error_details}</pre>
        <p>GitHub Actions loglarında bir ekran görüntüsü ve HTML kaynak dosyası oluşturulmuş olabilir. Lütfen kontrol ediniz.</p>
        """
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

def setup_selenium():
    """
    undetected-chromedriver kullanarak daha insan benzeri bir tarayıcı başlatır.
    """
    options = uc.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    # GitHub Actions ortamında chromedriver'ı bulabilmesi için
    driver = uc.Chrome(options=options, driver_executable_path=uc.find_chrome_executable())
    return driver

def search_and_extract_results(driver):
    """
    Sitedeki tüm personeli, A'dan Z'ye harf filtrelerine tıklayarak çeker.
    """
    try:
        logging.info("Siteye gidiliyor: https://rehber.maltepe.edu.tr/")
        driver.get("https://rehber.maltepe.edu.tr/")
        time.sleep(5) 

        letter_filters = WebDriverWait(driver, 20).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".main-search-filter-list .msfl-item"))
        )
        all_results = []
        collected_ids = set()

        for i in range(len(letter_filters)):
            filters = driver.find_elements(By.CSS_SELECTOR, ".main-search-filter-list .msfl-item")
            letter_filter = filters[i]
            letter = letter_filter.text
            logging.info(f"'{letter}' harfine tıklanıyor...")
            
            initial_result_count_text = driver.find_element(By.CSS_SELECTOR, ".search-results-count").text
            letter_filter.click()
            
            try:
                WebDriverWait(driver, 30).until_not(
                    EC.text_to_be_present_in_element((By.CSS_SELECTOR, ".search-results-count"), initial_result_count_text)
                )
            except TimeoutException:
                logging.warning(f"'{letter}' harfi için sonuçlar güncellenmedi veya hiç sonuç yok.")
                continue

            script = """
            const results = []; const rows = document.querySelectorAll('.search-results-list .srcl-column');
            rows.forEach(row => {
                const nameEl = row.querySelector('div:nth-child(2)');
                const surnameEl = row.querySelector('div:nth-child(3)');
                const unitEl = row.querySelector('.srl-item:nth-child(4) > a.unit');
                if (nameEl && surnameEl && unitEl) {
                    const name = nameEl.innerText.replace('Adı', '').trim();
                    const surname = surnameEl.innerText.replace('Soyadı', '').trim();
                    const unit = unitEl.innerText.trim();
                    const personId = `${name} ${surname}|${unit}`;
                    results.push({ 
                        'id': personId,
                        'data': { 'Ad Soyad': `${name} ${surname}`, 'Birim': unit }
                    });
                }
            });
            return results;
            """
            letter_results = driver.execute_script(script)

            for person in letter_results:
                if person['id'] not in collected_ids:
                    collected_ids.add(person['id'])
                    all_results.append(person['data'])
            
            logging.info(f"'{letter}' harfi için {len(letter_results)} sonuç bulundu. Toplam benzersiz sonuç: {len(all_results)}")
            time.sleep(2)

        return all_results

    except Exception as e:
        logging.error(f"Veri çekme fonksiyonunda bir hata oluştu: {e}")
        try:
            driver.save_screenshot(ERROR_SCREENSHOT_FILE)
            logging.info(f"Hata anı ekran görüntüsü '{ERROR_SCREENSHOT_FILE}' olarak kaydedildi.")
            with open(ERROR_HTML_FILE, 'w', encoding='utf-8') as f:
                f.write(driver.page_source)
            logging.info(f"Hata anı HTML kaynak kodu '{ERROR_HTML_FILE}' olarak kaydedildi.")
        except Exception as diag_e:
            logging.error(f"Teşhis dosyaları kaydedilirken ek bir hata oluştu: {diag_e}")
        raise e

def compare_lists(previous_list, current_list):
    get_id = lambda p: f"{p.get('Ad Soyad', '')}|{p.get('Birim', '')}"
    previous_ids = {get_id(p) for p in previous_list}
    previous_map = {get_id(p): p for p in previous_list}
    current_ids = {get_id(p) for p in current_list}
    current_map = {get_id(p): p for p in current_list}
    added_ids = current_ids - previous_ids
    removed_ids = previous_ids - current_ids
    added = [current_map[id] for id in added_ids]
    removed = [previous_map[id] for id in removed_ids]
    return added, removed

def analyze_statistics(personnel_list):
    stats = {}; stats['total_count'] = len(personnel_list)
    return stats

def main():
    setup_logging()
    logging.info("="*30); logging.info("Kontrol başlatıldı.")
    config = load_config()
    if not config: sys.exit(1)
    
    try:
        previous_results = []
        if os.path.exists(PERSISTENT_FILE):
            logging.info(f"Önceki personel listesi okunuyor: {PERSISTENT_FILE}")
            with open(PERSISTENT_FILE, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                previous_results = [row for row in reader if row]
        else:
            logging.warning(f"Önceki personel listesi ({PERSISTENT_FILE}) bulunamadı. Bu ilk çalıştırma olabilir.")
            
        logging.info("Tarayıcı başlatılıyor...")
        driver = setup_selenium()
        current_results = []
        try:
            current_results = search_and_extract_results(driver)
        finally:
            driver.quit()
            logging.info("Tarayıcı kapatıldı.")
            
        if not current_results:
            raise RuntimeError("Güncel personel listesi web sitesinden çekilemedi (boş liste döndü).")
        
        logging.info("Listeler karşılaştırılıyor...")
        added, removed = compare_lists(previous_results, current_results)
        statistics = analyze_statistics(current_results)
        
        if added or removed:
            logging.info("Değişiklikler tespit edildi. Rapor e-postası gönderiliyor...")
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
