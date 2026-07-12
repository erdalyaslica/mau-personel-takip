# Maltepe Üniversitesi Personel Takip

Maltepe Üniversitesi personel rehberini hafta içi her sabah kontrol eder. Yeni katılan veya ayrılan personel olduğunda e-posta, isteğe bağlı olarak Telegram bildirimi gönderir.

## Çalışma biçimi

- Rehber API'si Scrape.do üzerinden sorgulanır; Selenium/Chrome kullanılmaz.
- Altı sesli harfle alınan sonuçlar e-posta, ad-soyad ve birim bilgisine göre tekilleştirilir.
- Eksik tarama veya 50'den az kayıt durumunda mevcut liste değiştirilmez.
- İlk çalışmada güncel liste başlangıç verisi olarak saklanır ve toplu “yeni personel” bildirimi gönderilmez.
- Sonraki çalışmalarda yalnızca değişiklik varsa bildirim gönderilir.

## GitHub Secrets

Repository **Settings → Secrets and variables → Actions** bölümüne şunları ekleyin:

| Secret | Zorunlu | Açıklama |
|---|---:|---|
| `SCRAPEDO_TOKEN` | Evet | Scrape.do API anahtarı |
| `SENDER_EMAIL` | Evet | Gönderen Gmail adresi |
| `SENDER_PASSWORD` | Evet | Gmail uygulama şifresi |
| `RECEIVER_EMAILS` | Evet | Virgülle ayrılmış alıcılar |
| `TG_TOKEN` | Hayır | Telegram bot tokenı |
| `TG_ALLOWED_CHAT_ID` | Hayır | Bildirim gönderilecek sohbet kimliği |

İş akışı **Actions → Personel Rehber Kontrolü → Run workflow** ile elle denenebilir. Zamanlama hafta içi Türkiye saatiyle 09:10'dur (GitHub yoğunluğuna göre birkaç dakika gecikebilir).

Yerelde çalıştırmak için ortam değişkenlerini ayarlayıp `pip install -r requirements.txt` ve ardından `python mau_rehber.py` komutlarını kullanın.
