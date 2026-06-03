#!/usr/bin/env python3
"""End-to-End Test: RSS → Groq → WhatsApp (simuliert den n8n Workflow)."""

import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import re
import sys

import os
from pathlib import Path as _Path

def _load_dotenv(_path="/home/milan/.env"):
    """Lädt Secrets aus zentraler .env in os.environ (keine externe Abhängigkeit)."""
    try:
        for _l in _Path(_path).read_text().splitlines():
            _l = _l.strip()
            if not _l or _l.startswith("#") or "=" not in _l:
                continue
            _k, _v = _l.split("=", 1)
            _v = _v.strip()
            if len(_v) >= 2 and _v[0] in "\"'" and _v[-1] == _v[0]:
                _v = _v[1:-1]
            os.environ.setdefault(_k.strip(), _v)
    except FileNotFoundError:
        pass

_load_dotenv()

GROQ_KEY = os.environ["GROQ_API_KEY"]
EVOL_KEY = os.environ["EVOLUTION_API_KEY"]
WA_INST   = "milan-whatsapp"
WA_NUMBER = os.environ["WHATSAPP_NUMBER"]
import subprocess

RSS_FEEDS = [
    ("The Verge AI",      "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("TechCrunch AI",     "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("Ars Technica Tech", "https://feeds.arstechnica.com/arstechnica/technology-lab"),
    ("MIT Tech Review",   "https://www.technologyreview.com/feed/"),
    ("OpenAI News",       "https://openai.com/news/rss.xml"),
]

def fetch_url(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 n8n-rss-reader"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")

ATOM_NS = "http://www.w3.org/2005/Atom"

def strip_ns(tag):
    """Remove XML namespace from tag."""
    return re.sub(r"\{[^}]+\}", "", tag)

def el_text(el):
    if el is None:
        return ""
    # Handle CDATA / mixed content
    text = el.text or ""
    for child in el:
        text += (child.text or "") + (child.tail or "")
    return re.sub(r"<[^>]+>", "", text).strip()

def parse_rss(xml_text, source_name):
    items = []
    try:
        root = ET.fromstring(xml_text)
        root_tag = strip_ns(root.tag).lower()

        if root_tag == "feed":
            # Atom feed
            ns = {"a": ATOM_NS}
            entries = root.findall(f"{{{ATOM_NS}}}entry") or root.findall(".//entry")
            for entry in entries[:15]:
                title = el_text(entry.find(f"{{{ATOM_NS}}}title"))
                link_el = entry.find(f"{{{ATOM_NS}}}link[@rel='alternate']") or entry.find(f"{{{ATOM_NS}}}link")
                link = link_el.get("href", "") if link_el is not None else ""
                pub  = el_text(entry.find(f"{{{ATOM_NS}}}published") or entry.find(f"{{{ATOM_NS}}}updated"))
                desc = el_text(entry.find(f"{{{ATOM_NS}}}summary"))
                if not desc:
                    c = entry.find(f"{{{ATOM_NS}}}content")
                    desc = el_text(c)
        else:
            # RSS 2.0
            entries = root.findall(".//item")
            for entry in entries[:15]:
                def get(t):
                    e = entry.find(t)
                    return el_text(e)
                title = get("title")
                link  = get("link")
                pub   = get("pubDate") or get("dc:date")
                desc  = get("description") or get("summary")

        for entry in (entries[:15] if root_tag == "feed" else entries[:15]):
            # already processed above, collect results
            pass

        # rebuild cleanly
        items = []
        if root_tag == "feed":
            for entry in entries[:15]:
                title = el_text(entry.find(f"{{{ATOM_NS}}}title"))
                link_el = entry.find(f"{{{ATOM_NS}}}link[@rel='alternate']") or entry.find(f"{{{ATOM_NS}}}link")
                link = (link_el.get("href", "") if link_el is not None else "").split("?")[0]
                pub  = el_text(entry.find(f"{{{ATOM_NS}}}published") or entry.find(f"{{{ATOM_NS}}}updated"))
                summary_el = entry.find(f"{{{ATOM_NS}}}summary") or entry.find(f"{{{ATOM_NS}}}content")
                desc = re.sub(r"<[^>]+>", "", el_text(summary_el))[:300].strip()
                if title and link:
                    items.append({"title": title, "link": link, "pubDate": pub, "summary": desc, "source": source_name})
        else:
            for entry in entries[:15]:
                def get(t): return el_text(entry.find(t))
                title = get("title")
                link  = get("link").split("?")[0]
                pub   = get("pubDate") or get("dc:date")
                desc  = re.sub(r"<[^>]+>", "", get("description") or get("summary"))[:300].strip()
                if title and link:
                    items.append({"title": title, "link": link, "pubDate": pub, "summary": desc, "source": source_name})

    except Exception as e:
        print(f"  Parse error for {source_name}: {e}")
    return items

print("=" * 60)
print("KI News Digest – End-to-End Test (PostgreSQL Dedupe)")
print("=" * 60)

# Load already-seen URLs from PostgreSQL
try:
    result = subprocess.run(
        ["docker", "exec", "n8n-postgres", "psql", "-U", "n8n", "-d", "n8n", "-t", "-c",
         "SELECT url FROM ki_news_seen WHERE sent_at > NOW() - INTERVAL '7 days';"],
        capture_output=True, text=True, timeout=10
    )
    pg_seen = set(line.strip() for line in result.stdout.splitlines() if line.strip())
    print(f"  DB: {len(pg_seen)} bereits gesehene URLs aus PostgreSQL geladen")
except Exception as e:
    pg_seen = set()
    print(f"  ⚠️ PostgreSQL nicht erreichbar, fahre ohne DB fort: {e}")

# ── Step 1: Fetch RSS ────────────────────────────────────────
print("\n[1/4] Fetching RSS feeds...")
all_items = []
for name, url in RSS_FEEDS:
    try:
        xml = fetch_url(url)
        items = parse_rss(xml, name)
        print(f"  ✅ {name}: {len(items)} items")
        all_items.extend(items)
    except Exception as e:
        print(f"  ⚠️  {name}: {e}")

print(f"  Total: {len(all_items)} items across all feeds")

# ── Step 2: Filter & Dedupe ──────────────────────────────────
print("\n[2/4] Filtering & deduplicating...")
now = datetime.now(timezone.utc)
cutoff = now - timedelta(hours=13)

seen = set(pg_seen)  # Start with DB-seen URLs
fresh = []
for item in all_items:
    link = item["link"]
    if link in seen:
        continue
    seen.add(link)

    pub = item["pubDate"]
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(pub)
        if dt < cutoff:
            continue
    except Exception:
        pass  # keep if date unparseable

    fresh.append(item)

HIGH   = ['openai','anthropic','google deepmind','google gemini','meta ai','mistral','grok','xai',
          'benchmark','eval','mmlu','humaneval','swe-bench','arena','leaderboard',
          'api','release','launches','model','gpt','claude','gemini','llama',
          'reasoning','multimodal','agent','regulation','regulierung','eu ai act',
          'sicherheitslücke','vulnerability','breach','leaked','leak']
MEDIUM = ['microsoft','nvidia','apple','amazon','samsung','startup','funding',
          'raises','partnership','chip','hardware','open source','github']
LOW    = ['school','art','music','artist','culture','opinion','essay',
          'how to','guide','tips','review','hands-on']

def score(item):
    hay = (item['title'] + ' ' + item.get('summary','')).lower()
    if any(k in hay for k in LOW):    return 0
    if any(k in hay for k in HIGH):   return 2
    if any(k in hay for k in MEDIUM): return 1
    return 1

fresh.sort(key=lambda x: (score(x), x['pubDate']), reverse=True)
fresh = fresh[:7]
print(f"  Fresh items after filter: {len(fresh)}")
for item in fresh:
    print(f"    - [{item['source']}] {item['title'][:70]}")

if not fresh:
    print("\n⚠️  No fresh items found. The workflow would stop here.")
    print("   This is normal if all news is older than 13 hours.")
    print("   Sending a test message with mock data instead...")
    fresh = [{"title": "TEST: GPT-5 released", "link": "https://example.com/1",
              "pubDate": "", "summary": "This is a test entry to verify the pipeline works.", "source": "Test"}]

# ── Step 3: Groq Summarize ───────────────────────────────────
print("\n[3/4] Calling Groq API...")

utc_hour = now.hour
is_evening = utc_hour >= 12
header = "🌆 *KI News – Abendupdate*" if is_evening else "🌅 *KI News – Morgenupdate*"
date_str = now.strftime("%d.%m.%Y")

news_text = "\n\n".join(
    f"{i+1}. {item['title']}\n   {item['summary'][:180]}"
    for i, item in enumerate(fresh)
)

system_prompt = f"""Du bist ein KI-News-Redakteur für WhatsApp. Deine Ausgabe folgt exakt diesem Format:

{header} ({date_str})

• [Bullet]
• [Bullet]
• [Bullet]
• [Bullet]

🔥 *Wer gerade vorne ist*
– Overall: [Halbsatz]
– Coding: [Halbsatz]

Regeln für Bullets (4–6 Stück, nicht mehr, nicht weniger als 4):
- Jeder Bullet maximal 15 Wörter
- Aktive Sprache: "OpenAI startet X", "Anthropic veröffentlicht Y", "EU beschließt Z"
- Format: "[Wer] [tut was] – [knapper Fakt oder Konsequenz]"
- NUR für: Modell-Releases, API-Updates, Benchmarks, Regulierung, Sicherheitslücken, Firmennews mit direktem KI-Bezug

Absolute Verbote:
- KEIN "Dies ist wichtig, weil"
- KEIN "Dies ermöglicht es"
- KEIN "Dies zeigt"
- KEIN erklärender Nebensatz nach einem Komma (", was ...", ", um ...", ", der ...")
- KEIN "[4-6 Bullets]" oder andere Template-Notizen im Output

Für "🔥 Wer gerade vorne ist":
- Schreibe Overall und Coding NUR dann aus, wenn die gelieferten Artikel dafür eine konkrete Grundlage liefern (Benchmark, Release, direkter Vergleich).
- Wenn die Artikel keine belastbare Aussage erlauben, schreibe stattdessen exakt:
  🔥 *Wer gerade vorne ist* — heute keine belastbare Änderung
- KEIN freies Einschätzen aus Modellwissen. KEIN Halluzinieren von Rankings.
Sprache: Deutsch. Keine Erfindungen."""

user_prompt = f"Artikel:\n{news_text}"

groq_payload = json.dumps({
    "model": "llama-3.3-70b-versatile",
    "temperature": 0.1,
    "max_tokens": 500,
    "messages": [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ]
}).encode("utf-8")

req = urllib.request.Request(
    "https://api.groq.com/openai/v1/chat/completions",
    data=groq_payload,
    headers={
        "Authorization": f"Bearer {GROQ_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; n8n-workflow/1.0)",
        "Content-Length": str(len(groq_payload)),
    }
)

try:
    with urllib.request.urlopen(req, timeout=30) as r:
        groq_resp = json.loads(r.read())
    message_text = groq_resp["choices"][0]["message"]["content"].strip()
    print(f"  ✅ Groq OK ({groq_resp['usage']['total_tokens']} tokens)")
    print(f"\n{'─'*50}")
    print("GENERIERTER NACHRICHTENTEXT:")
    print("─"*50)
    print(message_text)
    print("─"*50)
except Exception as e:
    print(f"  ❌ Groq error: {e}")
    sys.exit(1)

# ── Step 4: Send WhatsApp ────────────────────────────────────
print("\n[4/4] Sending via WhatsApp (Evolution API)...")
wa_payload = json.dumps({"number": WA_NUMBER, "text": message_text}).encode("utf-8")
req = urllib.request.Request(
    f"http://milan:8089/message/sendText/{WA_INST}",
    data=wa_payload,
    headers={
        "apikey": EVOL_KEY,
        "Content-Type": "application/json"
    }
)
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        wa_resp = json.loads(r.read())
    msg_id = wa_resp.get("key", {}).get("id") or wa_resp.get("messageId") or "?"
    print(f"  ✅ WhatsApp gesendet! Message ID: {msg_id}")
except Exception as e:
    print(f"  ❌ WhatsApp error: {e}")
    sys.exit(1)

# Save sent URLs to PostgreSQL
print("\n  Speichere gesendete URLs in PostgreSQL...")
saved = 0
for item in fresh:
    try:
        link = item['link']
        title = item['title'].replace("'","''")
        source = item.get('source','').replace("'","''")
        subprocess.run(
            ["docker", "exec", "n8n-postgres", "psql", "-U", "n8n", "-d", "n8n", "-c",
             f"INSERT INTO ki_news_seen (url, title, source) VALUES ('{link}', '{title}', '{source}') ON CONFLICT DO NOTHING;"],
            capture_output=True, timeout=5
        )
        saved += 1
    except Exception:
        pass
print(f"  ✅ {saved} URLs in ki_news_seen gespeichert")

# Verify DB state
result = subprocess.run(
    ["docker", "exec", "n8n-postgres", "psql", "-U", "n8n", "-d", "n8n", "-t", "-c",
     "SELECT COUNT(*) FROM ki_news_seen;"],
    capture_output=True, text=True, timeout=5
)
total = result.stdout.strip()
print(f"  DB-Total: {total} Einträge in ki_news_seen")

print("\n✅ End-to-End Test erfolgreich!")
print("   Dedupe läuft jetzt über PostgreSQL (ki_news_seen)")
print("   Nächste automatische Ausführung: 08:30 und 17:30 CEST")
