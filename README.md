# Mau Personel Takip

Maltepe Üniversitesi personel rehberini hafta içi her sabah kontrol eder. Yeni katılan veya ayrılan personel olduğunda e-posta, isteğe bağlı olarak Telegram bildirimi gönderir.

## Çalışma biçimi

- Rehber API'si Scrape.do üzerinden sorgulanır; Selenium/Chrome kullanılmaz.
- Altı sesli harfle alınan sonuçlar e-posta, ad-soyad ve birim bilgisine göre tekilleştirilir.
- Eksik tarama veya 50'den az kayıt durumunda mevcut liste değiştirilmez.
- Güncel liste `rehber_durumu.csv` adıyla deponun Code/Files bölümünde tutulur.
- Her taramada site verisi bu CSV ile karşılaştırılır; değişiklik varsa bildirim gönderilir ve CSV güncellenir.
- CSV ayrıca ilgili Actions çalışmasında 30 gün indirilebilir dosya olarak sunulur.
- İlk çalışmada güncel liste başlangıç verisi olarak saklanır ve toplu “yeni personel” bildirimi gönderilmez.

## Kontrollü test

`rehber_durumu.csv` içinden bir satırı silip değişikliği doğrudan `main` dalına kaydedin. Ardından normal workflow çalıştırın. Silinen kişi “yeni katılan” olarak bildirilir ve otomasyon CSV dosyasını doğru hâline getirir.

## GitHub Secrets

Repository **Settings → Secrets and variables → Actions** bölümüne `SCRAPEDO_TOKEN`, `SENDER_EMAIL`, `SENDER_PASSWORD`, `RECEIVER_EMAILS` ve isteğe bağlı olarak `TG_TOKEN`, `TG_ALLOWED_CHAT_ID` eklenmelidir.

İş akışı **Actions → Personel Rehber Kontrolü → Run workflow** ile elle denenebilir. Zamanlama hafta içi Türkiye saatiyle 09:10'dur.
