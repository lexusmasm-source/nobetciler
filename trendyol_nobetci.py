#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trendyol Fırsat Nöbetçisi — 7/24 deal + kupon + stacking avcısı
================================================================
Trendyol'u periyodik tarar; BÜYÜK/GÜVENİLİR satıcıların ürünlerinde
aşağıdaki fırsat tiplerini yakalar ve Telegram'a anında bildirir:

  1) FIRSAT      : %50+ indirimli ürünler
  2) KUPON       : kupon rozeti olan ürünler
  3) STACKING    : indirim + kupon toplamı >= %80  -> "neredeyse bedava"
  4) FIYAT DÜŞÜŞÜ: takipteki ürün fiyatı >= %15 düştü

ZEKA KATMANI (v2.0):
  - SAHTE İNDİRİM DEDEKTÖRÜ: satıcının şişirdiği "çizili fiyat" tuzağını
    fiyat geçmişiyle yakalar. Etiket %60 indirim dese bile ürün geçmişte
    daha ucuza satılmışsa "ŞÜPHELİ" damgası yer.
  - GERÇEK FIRSAT ROZETİ: fiyat tarihi en düşük seviyedeyse
    "🏆 TARİHİ EN DÜŞÜK FİYAT" rozeti alır — bu en güçlü sinyaldir.
  - TREND ANALİZİ: son taramalardaki fiyat yönünü (📉 düşüş / 📈 yükseliş)
    bildirir; düşen üründe bekleme, yükselen üründe acele kararı verilir.

Satıcı güven filtresi (ikisinden biri yeterli):
  - Satıcı TRENDYOL_GUVENILIR_SATICILAR listesindeki resmi/büyük mağazalardan
  - veya ürün puanı >= MIN_URUN_PUANI (4.2) ve yorum sayısı >= MIN_YORUM_SAYISI (500)

Stdlib-only (harici bağımlılık yok). Modlar:
  --test      : çevrimdışı mantık testleri (örnek veri, internet yok)
  --once      : tek tarama, bulunan fırsatları stdout'a JSON yazar
  --tg-once   : tek tarama + Telegram'a gönder (GitHub Actions için)
  --loop N    : N saniyede bir sürekli tarama (varsayılan 600)

Env:
  TRENDYOL_ARANACAKLAR   : virgüllü arama terimleri (varsayılan geniş kategori listesi)
  MIN_INDIRIM_YUZDE      : fırsat eşiği (varsayılan 50)
  MIN_URUN_PUANI         : (varsayılan 4.2)
  MIN_YORUM_SAYISI       : (varsayılan 500)
  FIYAT_DUSUS_YUZDE      : fiyat düşüş alarm eşiği (varsayılan 15)
  STACKING_YUZDE         : stacking eşiği (varsayılan 80)
  TRENDYOL_GUVENILIR_SATICILAR : virgüllü beyaz liste (küçük harf eşleşir)
  TRENDYOL_STATE         : state dosyası yolu (varsayılan trendyol_state.json)
  TELEGRAM_BOT_TOKEN     : Telegram bildirimleri için
  TELEGRAM_CHAT_ID       : Telegram bildirimleri için
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import urllib.error

VERSION = "2.0.0"
STATE_FILE = os.getenv("TRENDYOL_STATE", os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "trendyol_state.json"))

# --- Trendyol arama API'si (trendyol.com ön yüzünün kullandığı uç) ---
SEARCH_BASE = ("https://public.trendyol.com/discovery-web-searchgw-service"
               "/v2/api/infinite-scroll/sr")
SEARCH_PARAMS = {
    "culture": "tr-TR", "userGenderId": "1", "channelId": "1", "pId": "0",
    "scoringAlgorithmId": "2", "categoryRelevancyEnabled": "false",
    "isLegalRequirementConfirmed": "false", "searchStrategyType": "DEFAULT",
    "productStampType": "TypeA", "fixSamplingForSpecialScenariosEnabled": "False",
}
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "tr-TR,tr;q=0.9",
    "culture": "tr-TR",
}

# Geniş kategori kapsamı: her döngüde bu terimler döndürülür (hepsi birden taranır).
DEFAULT_TERMS = (
    "bluetooth kulaklık,akıllı saat,laptop,tablet,akıllı telefon,"
    "robot süpürge,airfryer,kahve makinesi,ütü,saç kurutma makinesi,"
    "televizyon,oyun konsolu,klavye,mouse,monitör,"
    "spor ayakkabı,sneaker,çanta,cüzdan,güneş gözlüğü,parfüm,"
    "bebek bezi,bebek maması,oyuncak,lego,"
    "tava seti,düdüklü tencere,nevresim takımı,yorgan,battaniye,"
    "elektrikli scooter,bisiklet,dambıl,koşu bandı,"
    "krem,nemlendirici,şampuan,diş macunu,şampuan,"
    "kedi maması,köpek maması,akvaryum,"
    "deri ceket,mont,kaban,elbise,jean,"
    "kırtasiye,okul çantası,defter,"
    "powerbank,şarj aleti,kablo,ssd,disk"
)

# Resmi/büyük mağaza beyaz listesi (küçük harfle eşleşir)
DEFAULT_SELLERS_STR = (
    "trendyol,mediamarkt,teknosa,samsung,xiaomi,apple,philips,bosch,"
    "siemens,arçelik,beko,vestel,karaca,english home,madame coco,"
    "lc waikiki,defacto,koton,mavi,adidas,nike,puma,skechers,flo,"
    "boyner,morhipo,dyson,tefal,arzum,fakir,babyliss,braun,"
    "gilette,loreal,maybelline,nivea,elseve,head shoulders,"
    "sony,lg,jbl,anker,huawei,lenovo,hp,asus,monster,grundig,"
    "profilo,ferroli,demirdöküm,baymak,e.c.a,vitra,grohe,"
    "ikea,koçtaş,vivense,modalife,istikbal,bellona,"
    "decathlon,lescon,hummel,slazenger,kappa,lotto"
)


def _env(name, default, cast=str):
    v = os.getenv(name)
    if v is None or v == "":
        return default
    try:
        return cast(v)
    except Exception:
        return default


MIN_DISCOUNT = _env("MIN_INDIRIM_YUZDE", 50, int)
MIN_PRODUCT_RATING = _env("MIN_URUN_PUANI", 4.2, float)
MIN_RATING_COUNT = _env("MIN_YORUM_SAYISI", 500, int)
PRICE_DROP_PCT = _env("FIYAT_DUSUS_YUZDE", 15, int)
STACKING_PCT = _env("STACKING_YUZDE", 80, int)
TRUSTED_SELLERS = tuple(
    s.strip().lower() for s in _env(
        "TRENDYOL_GUVENILIR_SATICILAR", DEFAULT_SELLERS_STR).split(",")
    if s.strip())
SEARCH_TERMS = [t.strip() for t in
                _env("TRENDYOL_ARANACAKLAR", DEFAULT_TERMS).split(",") if t.strip()]
MAX_PAGES = _env("TRENDYOL_MAX_SAYFA", 3, int)
PER_PAGE = 24
REQ_SLEEP = _env("TRENDYOL_ISTEK_ARASI_SN", 1.2, float)
ALERT_COOLDOWN_H = 24        # aynı ürüne 24 saatte bir alarm (fiyat daha da düşmedikçe)
RE_ALERT_DROP_PCT = 10       # son alarmdan bu yana %10 daha düştüyse tekrar bildir

# --- Zeka katmanı ayarları ---
REAL_DEAL_TOL = _env("GERCEK_FIRSAT_TOLERANS", 1.02, float)   # bu katın altı = tarihi en düşük
FAKE_DISCOUNT_TOL = _env("SAHTE_INDIRIM_TOLERANS", 1.15, float)  # min fiyatın bu katı üstü = şişirilmiş
TREND_MIN_POINTS = _env("TRENDYOL_TREND_MIN", 3, int)          # trend için min gözlem sayısı
HIST_KEEP = 20  # ürün başına saklanan fiyat gözlemi

TIER_EMOJI = {"BEDAVA": "🚨", "KUPON": "🎟️", "FIRSAT": "🔥", "DUSUS": "📉"}


# ---------------------------------------------------------------- state
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {"products": {}, "updated": 0}


def save_state(state):
    state["updated"] = int(time.time())
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=0)
    os.replace(tmp, STATE_FILE)


# ---------------------------------------------------------------- fetch
def fetch_search_page(term, page):
    params = dict(SEARCH_PARAMS)
    params["q"] = term
    params["pi"] = str(page)
    url = SEARCH_BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def extract_products(payload):
    """sr-v2 cevabından ürün listesini savunmacı biçimde çıkarır."""
    if isinstance(payload, dict):
        result = payload.get("result") or payload.get("data") or {}
        if isinstance(result, dict):
            for key in ("products", "items", "contents"):
                if isinstance(result.get(key), list):
                    return result[key]
        if isinstance(payload.get("products"), list):
            return payload["products"]
    elif isinstance(payload, list):
        return payload
    return []


def _num(v, default=None):
    try:
        if v is None:
            return default
        return float(v)
    except Exception:
        return default


def _first(d, *keys):
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, "", 0):
            return d.get(k)
    return None


def normalize_product(p):
    """API ürün kaydını botun iç formatına çevirir; eksik alan -> None/0."""
    pid = str(p.get("id") or p.get("productId") or "")
    if not pid:
        return None
    price = p.get("price") or {}
    selling = _num(_first(price, "sellingPrice", "discountedPrice")
                   if isinstance(price, dict) else None)
    original = _num(_first(price, "originalPrice", "marketPrice")
                    if isinstance(price, dict) else None)
    if selling is None:
        selling = _num(p.get("price"))
    if selling is None or selling <= 0:
        return None
    if original is None or original <= selling:
        original = selling

    url = p.get("url") or ""
    if url and not url.startswith("http"):
        url = "https://www.trendyol.com" + url

    merchant = p.get("merchant") if isinstance(p.get("merchant"), dict) else {}
    merchant_name = (_first(p, "merchantName", "sellerName")
                     or _first(merchant, "name", "officialName") or "")

    # Rozet / promosyon metinleri: kupon ve sepette-% bilgisi buradan çıkarılır
    texts = []
    for key in ("badges", "promotions", "promotionBadges"):
        val = p.get(key)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    for f in ("title", "name", "text", "description"):
                        if item.get(f):
                            texts.append(str(item[f]))
                elif isinstance(item, str):
                    texts.append(item)
    for key in ("stamps",):
        val = p.get(key)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, dict) and item.get("text"):
                    texts.append(str(item["text"]))
    return {
        "id": pid,
        "name": str(p.get("name") or p.get("title") or "Ürün"),
        "url": url or f"https://www.trendyol.com/-p-{pid}",
        "selling": selling,
        "original": original,
        "discount_pct": round((original - selling) / original * 100) if original else 0,
        "rating": _num(_first(p, "ratingScore", "rating"), 0) or 0,
        "rating_count": int(_num(_first(p, "ratingCount", "reviewCount",
                                        "favoriteCount"), 0) or 0),
        "merchant": str(merchant_name),
        "merchant_id": str(p.get("merchantId") or merchant.get("id") or ""),
        "promo_texts": texts,
    }


def coupon_info(prod):
    """Rozet/promosyon metinlerinden kupon varlığı ve kupon yüzdesi çıkarır."""
    has_coupon = False
    coupon_pct = 0
    for t in prod.get("promo_texts") or []:
        low = t.lower()
        if "kupon" in low:
            has_coupon = True
        if "kupon" in low or "sepette" in low or "indirim" in low:
            m = re.search(r"%\s*(\d{1,2})", t)
            if m:
                coupon_pct = max(coupon_pct, int(m.group(1)))
    return has_coupon, coupon_pct


def _seller_whitelisted(name):
    # 4+ harfli isimler: alt-dize eşleşmesi ("samsung" ~ "Samsung Türkiye")
    # kısa isimler ("lg", "flo"): yanlış eşleşmeyi önlemek için tam eşitlik
    for s in TRUSTED_SELLERS:
        if len(s) >= 4 and s in name:
            return True
        if s == name:
            return True
    return False


def trusted_seller(prod):
    """Büyük/güvenilir satıcı filtresi."""
    name = (prod.get("merchant") or "").lower()
    if name and _seller_whitelisted(name):
        return True
    # Beyaz liste eşleşmezse: güçlü ürün puanı + çok yorum = köklü satış geçmişi
    return (prod.get("rating", 0) >= MIN_PRODUCT_RATING
            and prod.get("rating_count", 0) >= MIN_RATING_COUNT)


# ---------------------------------------------------------------- logic
def classify_price(prod, prev):
    """Fiyatın geçmişe göre GERÇEKLİĞİNİ sınıflandırır.
    Dönüş: (verdict, detay) ; verdict: GERCEK | NORMAL | SUPHELI | YENI
    """
    selling = prod["selling"]
    if not prev or not prev.get("min_price"):
        return "YENI", "ilk kez takipte"
    minp = prev["min_price"]
    if minp <= 0:
        return "YENI", "geçmiş fiyat yok"
    if selling <= minp * REAL_DEAL_TOL:
        return "GERCEK", (f"tarihi en düşük fiyat "
                          f"(önceki en düşük: {minp:,.0f} TL)")
    if selling > minp * FAKE_DISCOUNT_TOL:
        return "SUPHELI", (f"geçmişte {minp:,.0f} TL'ye satılmış, "
                           f"şu an {selling:,.0f} TL — indirim şişirilmiş olabilir")
    return "NORMAL", "fiyat geçmiş aralığında"


def price_trend(prev):
    """Son taramalardaki fiyat yönü. Dönüş: trend cümlesi | None"""
    hist = (prev or {}).get("price_hist") or []
    pts = [p for _, p in hist[-TREND_MIN_POINTS:]]
    if len(pts) < TREND_MIN_POINTS:
        return None
    if all(a > b for a, b in zip(pts, pts[1:])):
        return "📉 düşüş trendi (son taramalarda sürekli düştü — beklemek kârlı olabilir)"
    if all(a < b for a, b in zip(pts, pts[1:])):
        return "📈 yükseliş trendi (fiyat tırmanıyor — acele et)"
    return None


def evaluate(prod, prev):
    """Ürünü fırsat tiplerine göre değerlendirir.
    prev: state kaydı veya None.
    Dönüş: (tier, sebepler, trigger_price, verdict, verdict_detay) | None
    tier önceliği: BEDAVA > KUPON > FIRSAT > DUSUS
    """
    if not trusted_seller(prod):
        return None
    selling = prod["selling"]
    has_coupon, coupon_pct = coupon_info(prod)
    combined = prod["discount_pct"] + coupon_pct
    reasons = []

    tier = None
    if has_coupon and combined >= STACKING_PCT:
        tier = "BEDAVA"
        reasons.append(f"indirim %{prod['discount_pct']} + kupon %{coupon_pct} = %{combined}")
    elif has_coupon:
        tier = "KUPON"
        reasons.append("kuponlu ürün" + (f" (kupon %{coupon_pct})" if coupon_pct else ""))
    elif prod["discount_pct"] >= MIN_DISCOUNT:
        tier = "FIRSAT"
        reasons.append(f"%{prod['discount_pct']} indirim")
    if prev and prev.get("price") and selling > 0:
        drop = (prev["price"] - selling) / prev["price"] * 100
        if drop >= PRICE_DROP_PCT:
            reasons.append(f"takip fiyatı %{drop:.0f} düştü")
            if tier is None:
                tier = "DUSUS"
    if tier is None:
        return None

    # Alarm tekrarı kontrolü: 24 saat içinde, fiyat son alarmdan %10 daha
    # düşmedikçe aynı ürünü tekrar bildirme.
    now = time.time()
    if prev and prev.get("last_alert_ts"):
        age_h = (now - prev["last_alert_ts"]) / 3600
        last_price = prev.get("last_alert_price") or 0
        further_drop = ((last_price - selling) / last_price * 100
                        if last_price else 0)
        if age_h < ALERT_COOLDOWN_H and further_drop < RE_ALERT_DROP_PCT:
            return None

    # Zeka katmanı: geçmişe göre fiyatın gerçekliğini sınıflandır
    verdict, verdict_detay = classify_price(prod, prev)
    if verdict == "GERCEK":
        reasons.insert(0, f"🏆 TARİHİ EN DÜŞÜK FİYAT — {verdict_detay}")
    elif verdict == "SUPHELI":
        reasons.append(f"⚠️ ŞÜPHELİ İNDİRİM — {verdict_detay}")
    trend = price_trend(prev)
    if trend:
        reasons.append(trend)
    return tier, reasons, selling, verdict, verdict_detay


def fmt_alert(prod, tier, reasons, verdict="YENI", verdict_detay=""):
    emoji = TIER_EMOJI.get(tier, "🔥")
    tier_name = {
        "BEDAVA": "NERERESE BEDAVA (İNDİRİM+KUPON)",
        "KUPON": "KUPON FIRSATI",
        "FIRSAT": "BÜYÜK İNDİRİM",
        "DUSUS": "FİYAT DÜŞÜŞÜ",
    }.get(tier, tier)
    lines = [f"{emoji} <b>{tier_name}</b>"]
    if verdict == "GERCEK":
        lines.append("🏆 <b>GERÇEK FIRSAT — TARİHİ EN DÜŞÜK FİYAT</b>")
    elif verdict == "SUPHELI":
        lines.append("⚠️ <b>DİKKAT: İndirim şişirilmiş olabilir</b>")
    lines.append("")
    lines.append(f"🛍️ <b>{prod['name']}</b>")
    if prod.get("merchant"):
        lines.append(f"🏪 Satıcı: {prod['merchant']}")
    lines.append(f"💰 <b>{prod['selling']:,.2f} TL</b>"
                 + (f" (eski: {prod['original']:,.2f} TL, -%{prod['discount_pct']})"
                    if prod["original"] > prod["selling"] else ""))
    if prod.get("rating"):
        lines.append(f"⭐ {prod['rating']} ({prod['rating_count']} değerlendirme)")
    for r in reasons:
        lines.append(f"✅ {r}")
    lines.append("")
    lines.append(f"👉 {prod['url']}")
    lines.append("⏰ Stok/fiyat hızla değişebilir, hızlı davran.")
    return "\n".join(lines)


# ---------------------------------------------------------------- telegram
def send_telegram(text):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False, "TELEGRAM_BOT_TOKEN/CHAT_ID yok"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id, "text": text, "parse_mode": "HTML",
        "disable_web_page_preview": "false",
    }).encode()
    req = urllib.request.Request(url, data=data, headers={
        "User-Agent": "trendyol-nobetci/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return (r.status == 200), f"HTTP {r.status}"
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------- scan
def scan_once(state, terms=None, log=print):
    terms = terms or SEARCH_TERMS
    alerts = []
    seen_now = {}
    errors = 0
    for term in terms:
        for page in range(1, MAX_PAGES + 1):
            try:
                payload = fetch_search_page(term, page)
            except Exception as e:
                errors += 1
                log(f"[hata] '{term}' s{page}: {e}")
                break  # bu terimi geç, diğerine devam
            prods = extract_products(payload)
            if not prods:
                break
            for raw in prods:
                prod = normalize_product(raw)
                if not prod:
                    continue
                seen_now[prod["id"]] = prod
                prev = state["products"].get(prod["id"])
                result = evaluate(prod, prev)
                if result:
                    tier, reasons, price, verdict, verdict_detay = result
                    alerts.append({"tier": tier, "prod": prod,
                                   "reasons": reasons,
                                   "verdict": verdict,
                                   "verdict_detay": verdict_detay})
            if len(prods) < PER_PAGE:
                break
            time.sleep(REQ_SLEEP)
        time.sleep(REQ_SLEEP)
    # State güncelle: görülen her ürünün fiyat geçmişini zenginleştir
    now = int(time.time())
    for pid, prod in seen_now.items():
        old = state["products"].get(pid, {})
        hist = (old.get("price_hist") or []) + [[now, prod["selling"]]]
        rec = {
            "price": prod["selling"],
            "original": prod["original"],
            "name": prod["name"][:120],
            "last_seen": now,
            "first_seen": old.get("first_seen", now),
            "min_price": min(old.get("min_price", prod["selling"]),
                             prod["selling"]),
            "price_hist": hist[-HIST_KEEP:],
        }
        if old.get("last_alert_ts"):
            rec["last_alert_ts"] = old["last_alert_ts"]
            rec["last_alert_price"] = old.get("last_alert_price")
        state["products"][pid] = rec
    for a in alerts:
        rec = state["products"].get(a["prod"]["id"], {})
        rec["last_alert_ts"] = now
        rec["last_alert_price"] = a["prod"]["selling"]
        state["products"][a["prod"]["id"]] = rec
    # State şişmesini önle: 30 günden eski kayıtları at
    cutoff = int(time.time()) - 30 * 86400
    state["products"] = {k: v for k, v in state["products"].items()
                         if v.get("last_seen", 0) >= cutoff}
    return alerts, errors


def run_scan(send_tg=False):
    state = load_state()
    alerts, errors = scan_once(state)
    save_state(state)
    out = {"ts": int(time.time()), "version": VERSION,
           "scanned_terms": len(SEARCH_TERMS),
           "errors": errors, "alerts": []}
    for a in alerts:
        msg = fmt_alert(a["prod"], a["tier"], a["reasons"],
                        a.get("verdict", "YENI"), a.get("verdict_detay", ""))
        sent = None
        if send_tg:
            ok, info = send_telegram(msg)
            sent = {"ok": ok, "info": info}
        out["alerts"].append({
            "tier": a["tier"], "id": a["prod"]["id"],
            "name": a["prod"]["name"], "price": a["prod"]["selling"],
            "discount_pct": a["prod"]["discount_pct"],
            "merchant": a["prod"]["merchant"],
            "url": a["prod"]["url"], "message": msg,
            "verdict": a.get("verdict"), "verdict_detay": a.get("verdict_detay"),
            "telegram": sent})
    return out


# ---------------------------------------------------------------- tests
SAMPLE_PRODUCTS = [
    # 1) STACKING: %60 indirim + %30 kupon = %90 -> BEDAVA (resmi mağaza)
    {"id": 101, "name": "Test Ürün A (stacking)", "url": "/test-a-p-101",
     "price": {"sellingPrice": 400, "originalPrice": 1000},
     "ratingScore": 4.8, "ratingCount": 5200, "merchantName": "Trendyol",
     "badges": [{"title": "Kupona Özel %30 İndirim"}]},
    # 2) KUPON: kuponlu ama toplam eşik altında (yüksek puanlı ürün)
    {"id": 102, "name": "Test Ürün B (kupon)", "url": "/test-b-p-102",
     "price": {"sellingPrice": 700, "originalPrice": 1000},
     "ratingScore": 4.9, "ratingCount": 3000, "merchantName": "Bilindik Mağaza X",
     "badges": [{"title": "200 TL ve üzeri %10 kupon"}]},
    # 3) FIRSAT: %55 indirim, kuponsuz, güvenilir satıcı (MediaMarkt)
    {"id": 103, "name": "Test Ürün C (fırsat)", "url": "/test-c-p-103",
     "price": {"sellingPrice": 450, "originalPrice": 1000},
     "ratingScore": 4.5, "ratingCount": 900, "merchantName": "MediaMarkt",
     "badges": []},
    # 4) PAS: %70 indirim ama dandik satıcı (beyaz liste yok + düşük puan/az yorum)
    {"id": 104, "name": "Test Ürün D (dandik satıcı)", "url": "/test-d-p-104",
     "price": {"sellingPrice": 300, "originalPrice": 1000},
     "ratingScore": 3.1, "ratingCount": 12, "merchantName": "rastgele-butik-123",
     "badges": [{"title": "%50 kupon"}]},
    # 5) PAS: güvenilir ama indirim eşiğin altında, kupon yok
    {"id": 105, "name": "Test Ürün E (sıradan)", "url": "/test-e-p-105",
     "price": {"sellingPrice": 900, "originalPrice": 1000},
     "ratingScore": 4.7, "ratingCount": 8000, "merchantName": "Trendyol",
     "badges": []},
]


def run_tests():
    ok = fail = 0

    def check(name, cond):
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  ✅ {name}")
        else:
            fail += 1
            print(f"  ❌ {name}")

    prods = {p["id"]: normalize_product(p) for p in SAMPLE_PRODUCTS}
    check("normalize: 5 ürün de çevrildi", all(prods.values()))

    r = evaluate(prods[101], None)
    check("stacking -> BEDAVA", r and r[0] == "BEDAVA")
    r = evaluate(prods[102], None)
    check("kupon -> KUPON", r and r[0] == "KUPON")
    r = evaluate(prods[103], None)
    check("%55 indirim -> FIRSAT", r and r[0] == "FIRSAT")
    check("dandik satıcı elendi", evaluate(prods[104], None) is None)
    check("sıradan ürün elendi", evaluate(prods[105], None) is None)

    # Fiyat düşüşü: önceden 1000 TL görülen ürün 800 TL -> DUSUS (indirim yok)
    prod_drop = dict(prods[105])
    prod_drop["selling"] = 800
    prod_drop["original"] = 800
    prod_drop["discount_pct"] = 0
    r = evaluate(prod_drop, {"price": 1000})
    check("fiyat düşüşü -> DUSUS", r and r[0] == "DUSUS")

    # Cooldown: az önce alarm verilmiş, fiyat aynı -> tekrar yok
    prev = {"price": 400, "last_alert_ts": int(time.time()),
            "last_alert_price": 400}
    check("cooldown tekrarı engelledi", evaluate(prods[101], prev) is None)
    # Cooldown ama fiyat %20 daha düştü -> tekrar alarm
    prod_deeper = dict(prods[101])
    prod_deeper["selling"] = 320
    r = evaluate(prod_deeper, prev)
    check("derinleşen düşüş tekrar alarm verdi", r and r[0] == "BEDAVA")

    # Kupon ayrıştırma
    has_c, pct = coupon_info(prods[101])
    check("kupon tespiti + yüzde (%30)", has_c and pct == 30)
    has_c2, _ = coupon_info(prods[103])
    check("kuponsuz üründe kupon yok", not has_c2)

    # Alarm metni
    msg = fmt_alert(prods[101], "BEDAVA", ["indirim %60 + kupon %30 = %90"])
    check("alarm metni üretildi", "400" in msg and "trendyol.com" in msg)

    # ---- ZEKA KATMANI TESTLERİ (v2.0) ----
    # GERCEK: geçmiş min 400, şu an 390 -> tarihi en düşük
    prod_g = dict(prods[103])  # %55 indirim, MediaMarkt
    prod_g["selling"] = 390
    prev_g = {"price": 400, "min_price": 400,
              "price_hist": [[1, 500], [2, 450], [3, 400]]}
    r = evaluate(prod_g, prev_g)
    check("tarihi en düşük -> GERCEK", r and r[3] == "GERCEK")
    check("sebeplerde TARİHİ EN DÜŞÜK rozeti",
          r and any("TARİHİ EN DÜŞÜK" in s for s in r[1]))

    # SUPHELI: etiket %55 indirim ama geçmişte 300 TL'ye satılmış, şu an 450
    prod_s = dict(prods[103])
    prod_s["selling"] = 450
    prev_s = {"price": 450, "min_price": 300,
              "price_hist": [[1, 320], [2, 300], [3, 310]]}
    r = evaluate(prod_s, prev_s)
    check("şişirilmiş fiyat -> SUPHELI", r and r[3] == "SUPHELI")
    check("sebeplerde ŞÜPHELİ damgası",
          r and any("ŞÜPHELİ" in s for s in r[1]))

    # YENI: geçmiş yok
    r = evaluate(prods[103], None)
    check("geçmişsiz ürün -> YENI", r and r[3] == "YENI")

    # NORMAL: min 400, şu an 420 (%5 üstü) -> ne GERCEK ne SUPHELI
    prod_n = dict(prods[103])
    prod_n["selling"] = 420
    prev_n = {"price": 420, "min_price": 400}
    r = evaluate(prod_n, prev_n)
    check("aralık içi fiyat -> NORMAL", r and r[3] == "NORMAL")

    # Trend: düşen fiyatlar
    check("düşüş trendi yakalandı",
          price_trend(prev_g) is not None and "düşüş" in price_trend(prev_g))
    prev_up = {"price": 500, "min_price": 400,
               "price_hist": [[1, 400], [2, 450], [3, 500]]}
    check("yükseliş trendi yakalandı",
          price_trend(prev_up) is not None and "yükseliş" in price_trend(prev_up))
    check("yetersiz veri -> trend yok",
          price_trend({"price_hist": [[1, 400]]}) is None)

    # Alarm metni bannerları
    msg_g = fmt_alert(prod_g, "FIRSAT", r[1] if r else [], "GERCEK", "detay")
    check("GERCEK bannerı metinde", "GERÇEK FIRSAT" in msg_g)
    msg_s = fmt_alert(prod_s, "FIRSAT", ["x"], "SUPHELI", "detay")
    check("SUPHELI bannerı metinde", "şişirilmiş" in msg_s)

    # Telegram yapılandırma yoksa zarifçe False döner
    ok_tg, _ = send_telegram("test")
    check("telegram tokensız False", ok_tg is False)

    # State round-trip
    import tempfile
    global STATE_FILE
    old = STATE_FILE
    try:
        with tempfile.TemporaryDirectory() as td:
            STATE_FILE = os.path.join(td, "st.json")
            save_state({"products": {"1": {"price": 5}}, "updated": 0})
            check("state kaydedilip okundu", load_state()["products"]["1"]["price"] == 5)
    finally:
        STATE_FILE = old

    print(f"\nSONUÇ: {ok} başarılı, {fail} başarısız")
    return fail == 0


# ---------------------------------------------------------------- main
def main(argv):
    if "--test" in argv:
        return 0 if run_tests() else 1
    if "--once" in argv:
        out = run_scan(send_tg=False)
        print(json.dumps(out, ensure_ascii=False))
        return 0
    if "--tg-once" in argv:
        out = run_scan(send_tg=True)
        print(json.dumps(out, ensure_ascii=False))
        return 0
    if "--loop" in argv:
        idx = argv.index("--loop")
        interval = int(argv[idx + 1]) if len(argv) > idx + 1 else 600
        print(f"Trendyol Nöbetçisi v{VERSION} — {interval} sn aralıkla tarıyor. "
              f"Terimler: {len(SEARCH_TERMS)}, eşik: %{MIN_DISCOUNT}", flush=True)
        while True:
            try:
                out = run_scan(send_tg=True)
                for a in out["alerts"]:
                    print(a["message"], flush=True)
                    print("---", flush=True)
                print(f"[{time.strftime('%H:%M:%S')}] tarama bitti: "
                      f"{len(out['alerts'])} fırsat, {out['errors']} hata",
                      flush=True)
            except KeyboardInterrupt:
                return 0
            except Exception as e:
                print(f"[döngü hatası] {e}", flush=True)
            time.sleep(interval)
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
