# Personel Takip

Personel rehberini hafta içi sabah ve akşam kontrol eder. Yeni katılan veya ayrılan personel olduğunda e-posta, isteğe bağlı olarak Telegram bildirimi gönderir.

## Çalışma biçimi

- Rehber API'si Scrape.do üzerinden sorgulanır; Selenium/Chrome kullanılmaz.
- Altı sesli harfle alınan sonuçlar e-posta, ad-soyad ve birim bilgisine göre tekilleştirilir.
- Eksik tarama veya 50'den az kayıt durumunda mevcut liste değiştirilmez.
- Güncel liste `rehber_durumu.csv` adıyla deponun Code/Files bölümünde tutulur.
- Her taramada site verisi bu CSV ile karşılaştırılır; değişiklik varsa bildirim gönderilir ve CSV güncellenir.
- CSV ayrıca ilgili Actions çalışmasında 30 gün indirilebilir dosya olarak sunulur.
- İlk çalışmada güncel liste başlangıç verisi olarak saklanır ve toplu “yeni personel” bildirimi gönderilmez.

## Telegramdan anlık kontrol

Telegram botuna yalnızca yetkili sohbetten:

`/kontrol`

komutu gönderildiğinde rehber taraması başlatılır. GitHub Actions komutları yaklaşık 5 dakikada bir kontrol etmeyi dener; GitHub zamanlanmış çalışmaları geciktirebilir veya atlayabilir. Bekleyen komutu hemen işlemek için Actions → Personel Rehber Kontrolü → Run workflow bölümünde `process_telegram` seçeneğini açıp çalıştırın. Kontrol bittiğinde, değişiklik varsa ayrıntılı Telegram bildirimi; değişiklik yoksa tamamlanma mesajı gönderilir.

`/yardım` komutu kullanılabilir komutları gösterir.

## Kontrollü test

`rehber_durumu.csv` içinden bir satırı silip değişikliği doğrudan `main` dalına kaydedin. Ardından normal workflow çalıştırın. Silinen kişi “yeni katılan” olarak bildirilir ve otomasyon CSV dosyasını doğru hâline getirir.

## GitHub Secrets

Repository **Settings → Secrets and variables → Actions** bölümüne `SCRAPEDO_TOKEN`, `SENDER_EMAIL`, `SENDER_PASSWORD`, `RECEIVER_EMAILS` ve Telegram için `TG_TOKEN`, `TG_ALLOWED_CHAT_ID` eklenmelidir.

İş akışı [Personel Rehber Kontrolü](https://github.com/erdalyaslica/mau-personel-takip/actions/workflows/personel-rehber-kontrol.yml) üzerinden `Run workflow` ile elle denenebilir. `send_test_email` açık olursa yalnızca test e-postası gönderilir ve rehber taranmaz. Otomatik rehber kontrolü hafta içi Türkiye saatiyle 09:10 ve 18:10'da çalışır.
