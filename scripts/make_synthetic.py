"""Sentetik TEKNOFEST rapor PDF'leri üretir (pipeline testi için).

Üretilen senaryolar:
  1. saglik_ai_tam.pdf     — şablona tam uyumlu, sağlık kategorisi
  2. nlp_chatbot_tam.pdf   — şablona uyumlu, NLP kategorisi
  3. saglik_ai_kopya.pdf   — 1 numaranın parafrazlanmış kopyası (benzerlik testi)
  4. eksik_basliklar.pdf   — Yöntem, Riskler ve Kaynakça yok (şablon testi)
  5. yanlis_kategori.pdf   — içerik tarım, beyan sağlık (kategori uyum testi)
  6. ingilizce_rapor.pdf   — İngilizce yazılmış (dil kontrolü testi)

Kullanım:  python scripts/make_synthetic.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw"

TITLE_SIZE, HEAD_SIZE, BODY_SIZE = 18, 13.5, 10.5

# Base-14 PDF fontları Türkçe karakterleri (ı, ğ, ş, İ) taşımıyor.
# Gömülü TrueType font kullanıyoruz — gerçek TEKNOFEST raporları da böyle.
FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


#: Paragraf tekrar çarpanı — sentetik bölümleri gerçek PDR uzunluğuna yaklaştırır
LENGTH_FACTOR = 2


def _p(text: str, n: int = 1) -> str:
    return "\n\n".join([text] * (n * LENGTH_FACTOR))


SAGLIK = {
    "Proje Özeti (Proje Tanımı)": _p(
        "Bu proje, akciğer bilgisayarlı tomografi görüntüleri üzerinde nodül tespiti "
        "yapan derin öğrenme tabanlı bir klinik karar destek sistemi geliştirmeyi "
        "amaçlamaktadır. Sistem, radyoloji uzmanının incelediği kesitlerde şüpheli "
        "bölgeleri işaretleyerek tanı süresini kısaltmayı ve gözden kaçma oranını "
        "azaltmayı hedeflemektedir. Geliştirilen model, hastane bilgi yönetim "
        "sistemine PACS entegrasyonu ile bağlanacak ve raporlama ekranında "
        "uzmanın onayına sunulacaktır. Nihai tanı kararı her koşulda hekimde kalır; "
        "yapay zekâ yalnızca ön değerlendirme sunan bir destek katmanıdır.", 2),
    "Problem/Sorun": _p(
        "Türkiye'de radyoloji uzmanı başına düşen günlük tetkik sayısı sürekli "
        "artmakta, bu da inceleme süresinin kısalmasına ve küçük boyutlu nodüllerin "
        "gözden kaçmasına yol açmaktadır. Akciğer kanserinde erken evre teşhis, beş "
        "yıllık sağkalım oranını belirgin biçimde artırmaktadır. Mevcut iş akışında "
        "her tomografi serisi yüzlerce kesit içermekte ve uzman bu kesitleri manuel "
        "olarak taramaktadır. Bu manuel süreç hem zaman almakta hem de yorgunluğa "
        "bağlı hata riskini artırmaktadır.", 2),
    "Çözüm": _p(
        "Önerilen çözüm, üç aşamalı bir işlem hattıdır. Birinci aşamada tomografi "
        "kesitleri ön işlemden geçirilerek akciğer parankimi segmente edilir. İkinci "
        "aşamada 3B evrişimli sinir ağı mimarisi ile nodül adayları tespit edilir. "
        "Üçüncü aşamada yanlış pozitifleri azaltmak için sınıflandırıcı bir model "
        "çalıştırılır ve her aday için malignite olasılığı üretilir. Sonuçlar ısı "
        "haritası olarak orijinal kesit üzerine bindirilerek uzmana sunulur.", 2),
    "Yöntem": _p(
        "Model eğitimi için halka açık LIDC-IDRI veri seti ve kurum içi anonimleştirilmiş "
        "veri kullanılacaktır. Segmentasyon aşamasında U-Net mimarisi, tespit aşamasında "
        "3B ResNet omurgalı bir dedektör tercih edilmiştir. Eğitim sırasında veri "
        "artırma teknikleri olarak rastgele döndürme, ölçekleme ve yoğunluk pencereleme "
        "uygulanacaktır. Modelin başarımı duyarlılık, özgüllük ve FROC eğrisi altındaki "
        "alan ile ölçülecektir. Doğrulama beş katlı çapraz doğrulama ile yapılacak, "
        "sonuçlar bağımsız test kümesinde raporlanacaktır. Sistem PyTorch ile "
        "geliştirilecek, çıkarım için ONNX Runtime kullanılacaktır.", 3),
    "Yenilikçi (İnovatif) Yönü": _p(
        "Literatürdeki benzer çalışmalar çoğunlukla tek aşamalı tespit yapmakta ve "
        "yanlış pozitif oranı yüksek kalmaktadır. Projemizin özgün yönü, uzman geri "
        "bildirimini eğitim döngüsüne katan aktif öğrenme bileşenidir. Hekimin "
        "reddettiği aday bölgeler zor örnek havuzuna eklenerek model periyodik olarak "
        "güncellenir. Ayrıca kararların açıklanabilirliği için Grad-CAM tabanlı görsel "
        "gerekçe üretilmektedir.", 2),
    "Uygulanabilirlik": _p(
        "Sistem, mevcut PACS altyapısına DICOM standardı üzerinden entegre olacak "
        "şekilde tasarlanmıştır; hastanelerin donanım yatırımı yapması gerekmez. "
        "Pilot uygulama için bir üniversite hastanesi radyoloji anabilim dalı ile "
        "ön görüşme yapılmıştır. Ürünün tıbbi cihaz yazılımı olarak sınıflandırılması "
        "ve ilgili mevzuata uygun belgelendirme süreci planlanmıştır.", 2),
    "Tahmini Maliyet ve Proje Zaman Planlaması": _p(
        "Toplam tahmini maliyet 480.000 TL olup ana kalemler GPU sunucu kirası, veri "
        "etiketleme hizmeti ve yazılım geliştirme iş gücüdür. Proje on iki aya "
        "yayılmıştır: ilk üç ay veri toplama ve etiketleme, sonraki dört ay model "
        "geliştirme, takip eden üç ay entegrasyon ve son iki ay pilot uygulama ve "
        "değerlendirme olarak planlanmıştır.", 2),
    "Proje Fikrinin Hedef Kitlesi": _p(
        "Birincil hedef kitle, devlet ve üniversite hastanelerinin radyoloji "
        "birimleridir. İkincil hedef kitle, görüntüleme merkezleri ve tele-radyoloji "
        "hizmeti veren kuruluşlardır. Dolaylı fayda sağlayan grup ise erken teşhis "
        "sayesinde tedavi şansı artan hastalardır.", 2),
    "Riskler": _p(
        "En önemli risk, veri erişimi ve etik kurul onaylarının gecikmesidir; bu riske "
        "karşı halka açık veri setleriyle paralel çalışma planlanmıştır. İkinci risk, "
        "modelin farklı cihaz markalarında başarım kaybı yaşamasıdır; çoklu merkez "
        "verisiyle eğitim bu riski azaltacaktır. Üçüncü risk mevzuat sürecinin "
        "uzamasıdır.", 2),
    "Kaynakça": (
        "[1] Armato SG ve ark., The Lung Image Database Consortium, Medical Physics, 2011.\n"
        "[2] Ronneberger O. ve ark., U-Net: Convolutional Networks for Biomedical "
        "Image Segmentation, MICCAI, 2015.\n"
        "[3] Selvaraju RR ve ark., Grad-CAM, ICCV, 2017."
    ),
}

# 3 numara: 1'in parafrazlanmış hali (kelimeler değişti, anlam aynı)
SAGLIK_KOPYA = {
    "Proje Özeti (Proje Tanımı)": _p(
        "Çalışmamız, akciğer tomografi kesitleri üzerinde nodül saptayan derin "
        "öğrenme temelli bir klinik karar destek yazılımı geliştirmeyi hedeflemektedir. "
        "Yazılım, radyoloğun incelediği görüntülerde şüpheli alanları işaretleyerek "
        "tanı süresini azaltmayı ve atlanan bulgu oranını düşürmeyi amaçlar. "
        "Geliştirilen model hastane bilgi sistemine PACS bağlantısı ile entegre "
        "edilecek ve rapor ekranında hekimin onayına açılacaktır. Kesin tanı kararı "
        "daima hekime aittir; yapay zekâ yalnızca ön inceleme sağlayan yardımcı "
        "bir bileşendir.", 2),
    "Problem/Sorun": _p(
        "Ülkemizde radyoloji hekimi başına düşen günlük tetkik yükü giderek artmakta, "
        "bu durum inceleme süresini kısaltmakta ve küçük nodüllerin atlanmasına neden "
        "olmaktadır. Akciğer kanserinde erken evrede yakalama, beş yıllık sağkalımı "
        "önemli ölçüde yükseltmektedir. Bugünkü iş akışında her tomografi serisinde "
        "yüzlerce kesit bulunmakta ve hekim bunları elle taramaktadır. Bu elle yürüyen "
        "süreç hem zaman kaybına yol açmakta hem de yorgunluk kaynaklı hataları "
        "artırmaktadır.", 2),
    "Çözüm": _p(
        "Sunduğumuz çözüm üç aşamalı bir işlem zinciridir. İlk aşamada tomografi "
        "kesitlerine ön işlem uygulanarak akciğer dokusu ayrıştırılır. İkinci aşamada "
        "3B evrişimli sinir ağı mimarisiyle nodül adayları saptanır. Üçüncü aşamada "
        "yanlış pozitifleri düşürmek amacıyla bir sınıflandırma modeli çalıştırılır ve "
        "her aday için kötü huyluluk olasılığı hesaplanır. Bulgular ısı haritası "
        "biçiminde özgün kesit üzerine bindirilip hekime gösterilir.", 2),
    "Yöntem": _p(
        "Modelin eğitiminde kamuya açık LIDC-IDRI veri kümesi ve kurum içi "
        "anonimleştirilmiş kayıtlar kullanılacaktır. Ayrıştırma aşamasında U-Net "
        "mimarisi, saptama aşamasında 3B ResNet tabanlı bir dedektör seçilmiştir. "
        "Eğitimde veri çoğaltma yöntemi olarak rastgele döndürme, ölçekleme ve "
        "yoğunluk pencereleme kullanılacaktır. Başarım duyarlılık, özgüllük ve FROC "
        "eğrisi altındaki alanla değerlendirilecektir. Doğrulama beş katlı çapraz "
        "doğrulama ile gerçekleştirilecek, sonuçlar ayrık test kümesinde "
        "paylaşılacaktır.", 3),
    "Yenilikçi (İnovatif) Yönü": _p(
        "Alanyazındaki benzer çalışmalar genellikle tek aşamalı saptama yapmakta ve "
        "yanlış pozitif oranları yüksek seyretmektedir. Projemizin ayırt edici yönü, "
        "hekim geri bildirimini eğitim döngüsüne dahil eden aktif öğrenme modülüdür. "
        "Hekimin elediği aday bölgeler zor örnek havuzuna aktarılarak model düzenli "
        "aralıklarla yenilenir.", 2),
    "Uygulanabilirlik": _p(
        "Sistem, var olan PACS altyapısına DICOM standardı üzerinden bağlanacak "
        "biçimde kurgulanmıştır; hastanelerin ek donanım alması gerekmemektedir. "
        "Pilot çalışma için bir üniversite hastanesinin radyoloji bölümü ile ilk "
        "görüşmeler tamamlanmıştır.", 2),
    "Tahmini Maliyet ve Proje Zaman Planlaması": _p(
        "Toplam öngörülen bütçe 470.000 TL olup başlıca kalemler GPU sunucu kirası, "
        "veri etiketleme hizmeti ve yazılım geliştirme emeğidir. Proje on iki aylık "
        "takvime yayılmıştır.", 2),
    "Proje Fikrinin Hedef Kitlesi": _p(
        "Öncelikli hedef kitle devlet ve üniversite hastanelerinin radyoloji "
        "birimleridir. İkincil hedef kitle görüntüleme merkezleri ve tele-radyoloji "
        "kuruluşlarıdır.", 2),
    "Riskler": _p(
        "Başlıca risk, veriye erişim ve etik kurul onaylarındaki gecikmedir; buna "
        "karşı kamuya açık veri kümeleriyle koşut ilerleme planlanmıştır. Diğer risk "
        "modelin farklı cihazlarda başarım kaybetmesidir.", 2),
    "Kaynakça": (
        "[1] Armato SG et al., The Lung Image Database Consortium, Medical Physics, 2011.\n"
        "[2] Ronneberger O. et al., U-Net, MICCAI, 2015."
    ),
}

NLP = {
    "Proje Özeti (Proje Tanımı)": _p(
        "Bu proje, yarışma şartnameleri ve kılavuz belgeleri üzerinde çalışan, "
        "kaynak gösterebilen bir Türkçe soru cevaplama asistanı geliştirmeyi "
        "amaçlamaktadır. Sistem, kullanıcının serbest ifadeyle sorduğu soruyu "
        "anlamsal olarak eşleştirir, doğrulanmış belgelerden ilgili parçaları "
        "getirir ve yanıtı bu parçalara dayandırarak üretir.", 2),
    "Problem/Sorun": _p(
        "Sabit sık sorulan sorular listeleri, kullanıcıların farklı biçimlerde "
        "ifade ettiği soruları karşılayamamaktadır. Anahtar kelime eşleşmesine "
        "dayanan mevcut çözümler, aynı anlamı farklı kelimelerle taşıyan soruları "
        "kaçırmaktadır. Ayrıca içerik her dönem elle güncellenmekte, bu da eski "
        "bilgi riskini doğurmaktadır.", 2),
    "Çözüm": _p(
        "Çözümümüz, belgeleri anlamsal parçalara ayırıp vektör veritabanına "
        "yazan ve sorgu anında en ilgili parçaları getiren bir erişim artırılmış "
        "üretim mimarisidir. Yanıt üretiminde model yalnızca getirilen parçalara "
        "dayanır; yeterli kanıt bulunamazsa kesin yanıt vermek yerine kullanıcıyı "
        "insan desteğine yönlendirir.", 2),
    "Yöntem": _p(
        "Belgeler önce metin çıkarma katmanından geçirilir, başlık yapısı korunacak "
        "biçimde parçalara ayrılır ve çok dilli bir gömme modeliyle vektörleştirilir. "
        "Vektörler kosinüs benzerliği ile indekslenir. Sorgu anında hem yoğun vektör "
        "araması hem de anahtar kelime araması çalıştırılıp sonuçlar birleştirilir. "
        "Değerlendirme için kullanıcı sorularından oluşan bir test kümesi hazırlanmış, "
        "isabet oranı ve kaynak doğruluğu ölçülmüştür.", 3),
    "Yenilikçi (İnovatif) Yönü": _p(
        "Sistemin ayırt edici yönü, her yanıtın hangi belgeye ve hangi sayfaya "
        "dayandığını göstermesi ve güven seviyesi düşük olduğunda yanıt üretmekten "
        "kaçınmasıdır. Böylece uydurma bilgi riski belirgin biçimde azalmaktadır.", 2),
    "Uygulanabilirlik": _p(
        "Sistem açık kaynak bileşenlerle geliştirildiği için lisans maliyeti "
        "bulunmamaktadır. Kurum içi sunucuda çalıştırılabilmesi, veri gizliliği "
        "gereksinimlerini karşılamaktadır.", 2),
    "Tahmini Maliyet ve Proje Zaman Planlaması": _p(
        "Toplam maliyet 220.000 TL olarak öngörülmüştür. Proje altı aylık takvime "
        "yayılmış olup ilk iki ay veri hazırlığı, sonraki üç ay geliştirme ve son ay "
        "değerlendirme olarak planlanmıştır.", 2),
    "Proje Fikrinin Hedef Kitlesi": _p(
        "Hedef kitle, yarışmalara başvuran takımlar ve destek ekipleridir. İkincil "
        "kitle, benzer belge yoğun süreçleri yöneten kamu kurumlarıdır.", 2),
    "Riskler": _p(
        "Ana risk, kaynak belgelerin güncelliğini yitirmesidir; belge geçerlilik "
        "tarihi alanı ve pasife alma mekanizması bu riski yönetmektedir.", 2),
    "Kaynakça": "[1] Lewis P. et al., Retrieval-Augmented Generation, NeurIPS, 2020.",
}

TARIM_ICERIK = {
    "Proje Özeti (Proje Tanımı)": _p(
        "Bu proje, buğday tarlalarında pas hastalığını yaprak görüntülerinden tespit "
        "eden ve çiftçiye ilaçlama zamanı öneren bir hassas tarım sistemi "
        "geliştirmektedir. Sistem, tarlaya yerleştirilen toprak nem sensörleri ve "
        "insansız hava aracı ile toplanan çok bantlı görüntüleri birlikte "
        "değerlendirmektedir.", 2),
    "Problem/Sorun": _p(
        "Buğday üretiminde pas hastalığı geç fark edildiğinde verim kaybı yüzde "
        "kırka kadar çıkabilmektedir. Çiftçiler hastalık teşhisini görsel deneyime "
        "dayanarak yapmakta, bu da gereksiz ilaçlamaya veya geç müdahaleye yol "
        "açmaktadır. Aşırı ilaç kullanımı hem maliyeti hem çevresel etkiyi "
        "artırmaktadır.", 2),
    "Çözüm": _p(
        "Önerilen çözüm, yaprak görüntülerini sınıflandıran bir evrişimli sinir ağı "
        "ile toprak nem ve hava sıcaklığı verisini birleştiren bir karar motorudur. "
        "Sistem hastalık riskini günlük olarak hesaplar ve çiftçiye mobil bildirim "
        "gönderir. Sulama programı da toprak nemine göre otomatik ayarlanır.", 2),
    "Yöntem": _p(
        "Veri toplama için tarlaya kurulan sensör düğümleri LoRa protokolü ile "
        "verilerini toplayıcıya iletir. Görüntüler insansız hava aracına takılı çok "
        "bantlı kamera ile haftalık olarak alınır. Bitki sağlığı normalize edilmiş "
        "bitki örtüsü indeksi ile ölçülür. Hastalık sınıflandırması için transfer "
        "öğrenme yaklaşımıyla eğitilmiş bir model kullanılır. Ekin verimi tahmini "
        "için sezon boyu toplanan meteorolojik veriler regresyon modeline girdi "
        "olarak verilir.", 3),
    "Yenilikçi (İnovatif) Yönü": _p(
        "Mevcut çözümler yalnız görüntüye veya yalnız sensöre dayanmaktadır. "
        "Projemiz iki veri kaynağını birleştirerek yanlış alarm oranını "
        "düşürmektedir. Ayrıca sistem internet bağlantısı olmayan tarlalarda da "
        "yerel olarak çalışabilmektedir.", 2),
    "Uygulanabilirlik": _p(
        "Donanım maliyeti dekar başına düşük tutulmuş, tarım kredi kooperatifleri "
        "ile yaygınlaştırma modeli planlanmıştır. Çiftçi arayüzü sade tutulmuştur.", 2),
    "Tahmini Maliyet ve Proje Zaman Planlaması": _p(
        "Toplam maliyet 310.000 TL olup sensör donanımı ve insansız hava aracı ana "
        "kalemlerdir. Proje bir ekim sezonuna, yani dokuz aya yayılmıştır.", 2),
    "Proje Fikrinin Hedef Kitlesi": _p(
        "Hedef kitle orta ve büyük ölçekli buğday üreticileri ile tarım "
        "kooperatifleridir.", 2),
    "Riskler": _p(
        "Ana risk, sezon boyunca hastalık görülmemesi nedeniyle yeterli etiketli veri "
        "toplanamamasıdır; sera koşullarında kontrollü enfeksiyon denemesi yedek "
        "plandır.", 2),
    "Kaynakça": "[1] Mohanty SP et al., Using Deep Learning for Image-Based Plant "
                "Disease Detection, Frontiers in Plant Science, 2016.",
}

ENGLISH = {
    "Project Summary": _p(
        "This project develops an autonomous unmanned aerial vehicle capable of "
        "performing target detection during flight. The system integrates a flight "
        "control board with an onboard computer running a real time object detection "
        "model. The aim is to complete the competition mission autonomously without "
        "operator intervention.", 2),
    "Problem Statement": _p(
        "Current competition teams rely on manual piloting for target tracking, which "
        "introduces human reaction delay and reduces mission success rates. Autonomous "
        "operation requires reliable perception under vibration and changing "
        "illumination, which remains an open engineering challenge.", 2),
    "Solution": _p(
        "The proposed solution combines a lightweight detection network with a "
        "predictive tracking filter. The flight controller receives target coordinates "
        "and adjusts the trajectory to keep the target within the camera frame.", 2),
    "Method": _p(
        "The airframe is a fixed wing design with a wingspan of two meters. The flight "
        "controller runs an open source autopilot stack. The onboard computer performs "
        "inference at thirty frames per second. Telemetry is transmitted to the ground "
        "station over a long range radio link. Flight tests will be conducted in three "
        "stages: manual, assisted and fully autonomous.", 3),
    "Innovation": _p(
        "Unlike previous designs, our aircraft performs detection entirely onboard, "
        "removing dependence on the ground station link during the mission.", 2),
    "Feasibility": _p(
        "All components are commercially available and the total system cost remains "
        "within the team budget.", 2),
    "Cost and Timeline": _p(
        "The estimated cost is 250000 Turkish Lira. The project spans eight months "
        "including design, manufacturing and flight testing.", 2),
    "Target Audience": _p(
        "The primary audience consists of competition organisers and defence industry "
        "partners interested in autonomous platforms.", 2),
    "Risks": _p(
        "The main risk is airframe damage during autonomous test flights; a spare "
        "airframe has been budgeted.", 2),
    "References": "[1] Redmon J. et al., You Only Look Once, CVPR, 2016.",
}



SIBER = {
    "Proje Özeti (Proje Tanımı)": _p(
        "Bu proje, kurumsal ağ trafiğinde anomali tespiti yapan ve saldırı "
        "girişimlerini gerçek zamanlı olarak işaretleyen bir güvenlik izleme "
        "sistemi geliştirmeyi amaçlamaktadır. Sistem, akan trafik üzerinde "
        "denetimsiz öğrenme yöntemleriyle olağandışı davranışları saptar ve "
        "güvenlik ekibine önceliklendirilmiş uyarı üretir.", 2),
    "Problem/Sorun": _p(
        "Kurumsal ağlarda üretilen günlük kayıt hacmi, güvenlik ekiplerinin "
        "elle inceleyebileceği sınırın çok üzerindedir. İmza tabanlı saldırı "
        "tespit sistemleri yalnızca bilinen saldırı kalıplarını yakalayabilmekte, "
        "sıfırıncı gün saldırıları gözden kaçmaktadır. Yanlış alarm oranının "
        "yüksekliği ise ekiplerde uyarı yorgunluğuna yol açmaktadır.", 2),
    "Çözüm": _p(
        "Önerilen çözüm, ağ akış kayıtlarını özellik vektörlerine dönüştüren ve "
        "izolasyon ormanı ile otomatik kodlayıcı modellerini birlikte kullanan "
        "bir anomali tespit hattıdır. Uyarılar risk skoruna göre sıralanır ve "
        "her uyarı için hangi özelliğin anomaliye yol açtığı gösterilir.", 2),
    "Yöntem": _p(
        "Ağ akış kayıtları NetFlow biçiminde toplanır ve zaman pencereleri "
        "halinde özetlenir. Öznitelik olarak paket sayısı, bayt hacmi, port "
        "dağılımı ve bağlantı süresi kullanılır. Model eğitimi saldırısız trafik "
        "üzerinde yapılır. Başarım ölçümünde kesinlik, duyarlılık ve yanlış alarm "
        "oranı raporlanır.", 3),
    "Yenilikçi (İnovatif) Yönü": _p(
        "Projenin ayırt edici yönü, tespit edilen anomali için açıklanabilir "
        "gerekçe üretmesi ve güvenlik analistinin geri bildirimini modele geri "
        "beslemesidir.", 2),
    "Uygulanabilirlik": _p(
        "Sistem mevcut günlük toplama altyapısına eklenti olarak kurulabilir; "
        "ağ topolojisinde değişiklik gerektirmez.", 2),
    "Tahmini Maliyet ve Proje Zaman Planlaması": _p(
        "Toplam maliyet 190.000 TL olarak öngörülmüştür. Proje yedi aya "
        "yayılmıştır.", 2),
    "Proje Fikrinin Hedef Kitlesi": _p(
        "Hedef kitle, kurumsal güvenlik operasyon merkezleri ve yönetilen "
        "güvenlik hizmeti sağlayıcılarıdır.", 2),
    "Riskler": _p(
        "Ana risk, eğitim verisinde gizli saldırı trafiği bulunmasıdır.", 2),
    "Kaynakça": "[1] Liu FT et al., Isolation Forest, ICDM, 2008.",
}

def build_pdf(path: Path, title: str, sections: dict[str, str],
              numbered: bool = True) -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    y = 60.0
    margin, width = 56.0, 483.0

    page.insert_textbox(
        pymupdf.Rect(margin, y, margin + width, y + 70),
        title, fontsize=TITLE_SIZE, fontname="TRB", fontfile=FONT_BOLD, align=1,
    )
    y += 80

    for i, (head, body) in enumerate(sections.items(), start=1):
        head_text = f"{i}. {head}" if numbered else head
        need = 30
        if y + need > 780:
            page = doc.new_page()
            y = 60
        page.insert_textbox(
            pymupdf.Rect(margin, y, margin + width, y + 26),
            head_text, fontsize=HEAD_SIZE, fontname="TRB", fontfile=FONT_BOLD,
        )
        y += 28

        for para in body.split("\n\n"):
            para = para.strip()
            if not para:
                continue
            # Paragrafın kabaca kaç satır süreceğini tahmin et (satır ~95 karakter)
            est_height = (len(para) / 95 + 1) * (BODY_SIZE * 1.35)
            if y + est_height > 770:
                page = doc.new_page()
                y = 60.0
            bottom = min(y + est_height + 40, 790.0)
            rect = pymupdf.Rect(margin, y, margin + width, bottom)
            height = page.insert_textbox(
                rect, para, fontsize=BODY_SIZE, fontname="TRR", fontfile=FONT_REGULAR, align=3
            )
            if height < 0:  # yine sığmadı -> tam sayfa dene
                page = doc.new_page()
                y = 60.0
                rect = pymupdf.Rect(margin, y, margin + width, 790.0)
                height = page.insert_textbox(
                    rect, para, fontsize=BODY_SIZE, fontname="TRR", fontfile=FONT_REGULAR, align=3
                )
            used = (rect.y1 - y) - max(height, 0)
            y += used + 10
        y += 8

    doc.set_metadata({"title": title, "author": "T-Sistem Sentetik Veri"})
    doc.save(path)
    doc.close()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = [
        ("saglik_ai_tam.pdf", "Akciğer Nodül Tespiti İçin Klinik Karar Destek Sistemi", SAGLIK),
        ("nlp_chatbot_tam.pdf", "Kaynak Gösteren Türkçe Soru Cevaplama Asistanı", NLP),
        ("saglik_ai_kopya.pdf", "Tomografi Görüntülerinde Nodül Saptama Sistemi", SAGLIK_KOPYA),
        ("yanlis_kategori.pdf", "Buğdayda Pas Hastalığı Erken Uyarı Sistemi", TARIM_ICERIK),
        ("ingilizce_rapor.pdf", "Autonomous Target Detection UAV", ENGLISH),
    ]
    for name, title, content in jobs:
        build_pdf(OUT / name, title, content)
        print(f"  ✓ {name}")

    # Eksik başlıklı varyant — benzerlik testini kirletmemesi için
    # bağımsız bir içerikten (siber güvenlik) türetiliyor.
    eksik = {k: v for k, v in SIBER.items()
             if k not in ("Yöntem", "Riskler", "Kaynakça")}
    build_pdf(OUT / "eksik_basliklar.pdf", "Eksik Bölümlü Örnek Rapor", eksik)
    print("  ✓ eksik_basliklar.pdf")

    print(f"\n{len(jobs) + 1} PDF üretildi: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
