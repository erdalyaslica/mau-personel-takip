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

komutu gönderildiğinde rehber taraması başlatılır. GitHub Actions yeni komutları yaklaşık 5 dakikada bir kontrol eder; GitHub yoğunluğunda gecikme olabilir. Kontrol bittiğinde, değişiklik varsa ayrıntılı Telegram bildirimi; değişiklik yoksa tamamlanma mesajı gönderilir.

`/yardım` komutu kullanılabilir komutları gösterir.

## Sürekli Telegram servisine geçiş

`telegram_service.py` tek örnek olarak kurulacak bir arka plan servisidir.
`/kontrol` (`kontrol`) ve `/son5` (`son 5`) komutlarını Telegram uzun yoklama
bağlantısıyla alır. `/kontrol` tarama başında ve sonunda ayrı mesaj yollar;
güncel listeyi GitHub'a kaydeder. `/son5` CSV dosyasının GitHub commit
geçmişini okur. Yetkili sohbet dışındaki komutlar işlenmez.

Docker destekleyen ve sürekli çalışan bir **background worker** kurun (depo
kökündeki `Dockerfile` kullanılır). Tek örnek çalıştırın ve şunları yalnızca
barındırma sağlayıcısının gizli ortam değişkenlerine girin:

| Değişken | Amaç |
| --- | --- |
| `TG_TOKEN` | Mevcut Telegram botunun anahtarı |
| `TG_ALLOWED_CHAT_ID` | Yetkili sohbet numarası |
| `SCRAPEDO_TOKEN` | Rehber taraması |
| `GH_TOKEN` | Bu depoya **Contents: Read and write** izni olan fine-grained GitHub token |
| `GH_REPOSITORY` | İsteğe bağlı; varsayılan `erdalyaslica/mau-personel-takip` |
| `GH_BRANCH` | İsteğe bağlı; varsayılan `main` |
| `SENDER_EMAIL`, `SENDER_PASSWORD`, `RECEIVER_EMAILS` | `/kontrol` değişikliklerinin e-posta bildirimi isteniyorsa üçü birden |

Tokenları depoya veya Docker imajına yazmayın. Mevcut `TG_TOKEN` ve
`TG_ALLOWED_CHAT_ID` değerleri GitHub Actions Secrets içinde tutulmaya devam
eder: planlı tarama bildirim göndermeye devam eder. Servis çalışırken önce
`/yardım`, `/son5` ve `/kontrol` yanıtlarını deneyin. Başarılı canlı
doğrulamadan **sonra** Actions'taki `*/5` komut yoklamasını kaldırın; iki
tüketici aynı anda `getUpdates` çağırmamalıdır. Hafta içi sabah ve akşam
taraması Actions'ta kalır.

## Kontrollü test

`rehber_durumu.csv` içinden bir satırı silip değişikliği doğrudan `main` dalına kaydedin. Ardından normal workflow çalıştırın. Silinen kişi “yeni katılan” olarak bildirilir ve otomasyon CSV dosyasını doğru hâline getirir.

## GitHub Secrets

Repository **Settings → Secrets and variables → Actions** bölümüne `SCRAPEDO_TOKEN`, `SENDER_EMAIL`, `SENDER_PASSWORD`, `RECEIVER_EMAILS` ve Telegram için `TG_TOKEN`, `TG_ALLOWED_CHAT_ID` eklenmelidir.

İş akışı [Personel Rehber Kontrolü](https://github.com/erdalyaslica/mau-personel-takip/actions/workflows/personel-rehber-kontrol.yml) üzerinden `Run workflow` ile elle denenebilir. `send_test_email` açık olursa yalnızca test e-postası gönderilir ve rehber taranmaz. Otomatik rehber kontrolü hafta içi Türkiye saatiyle 09:10 ve 18:10'da çalışır.
