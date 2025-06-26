# Gerekli kütüphaneleri içe aktar
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
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
ERROR_HTML_FILE = 'error_page_source.html' # Hata anındaki HTML'i kaydetmek için

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
    chrome_options = Options()
    chrome_options.add_argument("--headless"); chrome_options.add_argument("--disable-gpu"); chrome_options.add_argument("--window-size=1920x1080"); chrome_options.add_argument("--no-sandbox"); chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled"); chrome_options.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36")
    service = Service(ChromeDriverManager().install()); driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": "Object.defineProperty(navigator, 'webdriver', { get: () => undefined })"})
    return driver

def search_and_extract_results(driver):
    try:
        logging.info("Siteye gidiliyor: https://rehber.maltepe.edu.tr/")
        driver.get("https://rehber.maltepe.edu.tr/")
        # Sayfanın oturması için kısa bir bekleme
        time.sleep(5)
        
        logging.info("Cookie butonunu arıyor...")
        try:
            WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, '//button[contains(text(), "Kabul Et")]'))).click()
            logging.info("Cookie kabul edildi.")
        except Exception: 
            logging.info("Cookie kutusu bulunamadı veya zaten kapalı.")

        logging.info("Arama kutusunu arıyor...")
        search_box = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "search-key")))
        search_box.clear()
        search_box.send_keys(" ")
        
        logging.info("Arama butonunu arıyor...")
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "search-button"))).click()
        logging.info("Arama yapıldı.")
        
        logging.info("Arama sonuçlarının yüklenmesi bekleniyor (en fazla 90 saniye)...")
        WebDriverWait(driver, 90).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".search-results-list .srcl-column")))
        logging.info("Arama sonuçları yüklendi.")
        
        script = """
        const results = []; const rows = document.querySelectorAll('.search-results-list .srcl-column');
        rows.forEach(row => {
            const nameEl = row.querySelector('div:nth-child(2)'); const surnameEl = row.querySelector('div:nth-child(3)');
            const unitEl = row.querySelector('.unit');
            if (nameEl && surnameEl && unitEl) {
                const name = nameEl.innerText.replace('Adı', '').trim(); const surname = surnameEl.innerText.replace('Soyadı', '').trim();
                const unit = unitEl.innerText.trim();
                results.push({ 'Ad Soyad': `${name} ${surname}`, 'Birim': unit });
            }
        });
        return results;
        """
        return driver.execute_script(script)

    except Exception as e:
        # --- HATA YAKALAMA BÖLÜMÜ ---
        logging.error(f"Veri çekme fonksiyonunda bir hata oluştu: {e}")
        
        # Ekran görüntüsü al
        try:
            driver.save_screenshot(ERROR_SCREENSHOT_FILE)
            logging.info(f"Hata anı ekran görüntüsü '{ERROR_SCREENSHOT_FILE}' olarak kaydedildi.")
        except Exception as screenshot_e:
            logging.error(f"Ekran görüntüsü alınırken hata oluştu: {screenshot_e}")
            
        # HTML kaynak kodunu al
        try:
            with open(ERROR_HTML_FILE, 'w', encoding='utf-8') as f:
                f.write(driver.page_source)
            logging.info(f"Hata anı HTML kaynak kodu '{ERROR_HTML_FILE}' olarak kaydedildi.")
        except Exception as html_e:
            logging.error(f"HTML kaynak kodu alınırken hata oluştu: {html_e}")

        # Orijinal hatayı yeniden yükselt
        raise e

# Diğer fonksiyonlar (compare_lists, analyze_statistics, main) aynı kalabilir
def compare_lists(previous_list, current_list):
    previous_set = {tuple(p.items()) for p in previous_list}; current_set = {tuple(p.items()) for p in current_list}
    return [dict(p) for p in current_set - previous_set], [dict(p) for p in previous_set - current_set]
def analyze_statistics(personnel_list):
    stats = {}; stats['total_count'] = len(personnel_list)
    return stats
def main():
    """Programın ana giriş noktası."""
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
                previous_results = list(reader)
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
