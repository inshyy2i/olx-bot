import json, os, sys, time
from pathlib import Path
import requests
from bs4 import BeautifulSoup

TG_TOKEN = os.environ.get("TG_TOKEN", "")
TG_CHAT = os.environ.get("TG_CHAT", "")

CITY = "szczecin"
RADIUS_KM = 40
QUERIES = ["telewizor", "tv", "smart tv", "telewizor lg", "telewizor samsung"]
INTERVAL_SEC = 120
SEEN_FILE = Path(__file__).with_name("seen.json")

BROKEN_WORDS = ["uszkodz", "zepsut", "na części", "na czesci", "rozbit", "pęknięt",
    "peknie", "popsut", "nie działa", "nie dziala", "bez obrazu", "do naprawy", "do remontu"]
NOT_TV_WORDS = ["szafka", "stolik", "stojak", "uchwyt", "pilot do", "komoda",
    "regał", "regal", "ława", "lawa", "podstawka", "kabel", "antena",
    "dekoder", "soundbar", "monitor"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Accept-Language": "pl-PL,pl;q=0.9",
}

def search_url(query):
    q = query.replace(" ", "-")
    return f"https://www.olx.pl/oddam-za-darmo/{CITY}/q-{q}/?search%5Bdist%5D={RADIUS_KM}&search%5Border%5D=created_at%3Adesc"

def fetch_listings(query):
    r = requests.get(search_url(query), headers=HEADERS, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    out = []
    for card in soup.select('div[data-cy="l-card"]'):
        a = card.find("a", href=True)
        if not a or "/d/oferta/" not in a["href"]:
            continue
        href = a["href"]
        url = href if href.startswith("http") else "https://www.olx.pl" + href
        url = url.split("#")[0].split("?")[0]
        t = card.find(["h4", "h6", "h3"])
        title = t.get_text(" ", strip=True) if t else a.get_text(" ", strip=True)
        l = card.select_one('[data-testid="location-date"]')
        loc = l.get_text(" ", strip=True) if l else ""
        img = card.find("img")
        img_url = img.get("src") if img and img.get("src", "").startswith("http") else None
        out.append({"url": url, "title": title, "loc": loc, "img": img_url})
    return out

def classify(title):
    t = title.lower()
    if any(w in t for w in NOT_TV_WORDS): return "skip"
    if any(w in t for w in BROKEN_WORDS): return "broken"
    return "ok"

def tg_text(text):
    requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                  data={"chat_id": TG_CHAT, "text": text}, timeout=20)

def tg_send(item, status):
    mark = "⚠️ можливо зламаний" if status == "broken" else "✅ схоже на робочий / без опису"
    text = f"📺 {item['title']}\n{item['loc']}\n{mark}\n{item['url']}"
    if item.get("img"):
        r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto",
            data={"chat_id": TG_CHAT, "photo": item["img"], "caption": text}, timeout=20)
        if r.ok: return
    tg_text(text)

def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return None

def run_once(seen, first_run):
    new = 0
    for q in QUERIES:
        try:
            items = fetch_listings(q)
        except Exception as e:
            print(f"[{q}] помилка: {e}", file=sys.stderr)
            continue
        print(f"[{q}] знайдено на сторінці: {len(items)}")
        for it in items:
            if it["url"] in seen: continue
            seen.add(it["url"])
            st = classify(it["title"])
            if st == "skip": continue
            if not first_run:
                tg_send(it, st)
                new += 1
        time.sleep(3)
    SEEN_FILE.write_text(json.dumps(sorted(seen)))
    return new

def main():
    if not TG_TOKEN or not TG_CHAT:
        sys.exit("Задай TG_TOKEN і TG_CHAT")
    seen = load_seen()
    first_run = seen is None
    seen = seen or set()
    if os.environ.get("GITHUB_ACTIONS"):
        print("нових:", run_once(seen, first_run))
        return
    tg_text("🤖 Бот запущено, шукаю безкоштовні телевізори біля Щецина.")
    while True:
        n = run_once(seen, first_run)
        first_run = False
        print(time.strftime("%H:%M:%S"), "нових:", n)
        time.sleep(INTERVAL_SEC)

main()
