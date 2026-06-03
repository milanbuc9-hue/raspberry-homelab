#!/usr/bin/env python3
"""
Rebuild KI-News-Digest Workflow:
- Dedupe via PostgreSQL table ki_news_seen (statt staticData)
- Fallback: bei 0 frischen Items → stiller Stop (keine halbfrischen News)
"""

import json, uuid, urllib.request, urllib.error, sys

N8N_URL  = "http://milan:5678"
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

JWT_KEY = os.environ["N8N_JWT_KEY"]
GROQ_KEY = os.environ["GROQ_API_KEY"]
TG_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TG_CHAT  = "6372069186"
PG_CRED  = "OTNan4YOEPjohRvs"
WF_ID    = open("/home/milan/scripts/.ai-news-workflow-id").read().strip()

def uid(): return str(uuid.uuid4())

# ── Code: Filter (nutzt PostgreSQL-Daten + RSS-Items im gleichen Input) ──────
FILTER_CODE = r"""
const allItems = $input.all();

// Trenne PostgreSQL-Seen-URLs von echten RSS-Items
// PG-Items: haben 'url' (SELECT url FROM ki_news_seen)
// RSS-Items: haben 'title' und 'link'
const seenUrls = new Set();
const rssItems = [];

for (const item of allItems) {
  const j = item.json;
  if (j.url && !j.title) {
    // PostgreSQL-Row: gesehene URL
    seenUrls.add(j.url);
  } else if (j.link || j.title) {
    // RSS-Item
    rssItems.push(j);
  }
}

const now = new Date();
const utcHour = now.getUTCHours();
const isEvening = utcHour >= 12;
const header = isEvening ? '🌆 *KI News – Abendupdate*' : '🌅 *KI News – Morgenupdate*';

// Zeitfenster: letzten 13h (deckt beide Slots sicher ab)
const cutoffMs = 13 * 60 * 60 * 1000;

const seenInRun = new Set();
const fresh = [];

for (const j of rssItems) {
  const link = (j.link || j.url || '').trim().split('?')[0].split('#')[0];
  if (!link) continue;
  if (seenUrls.has(link)) continue;       // bereits in DB → überspringen
  if (seenInRun.has(link)) continue;      // Duplikat in diesem Run → überspringen
  seenInRun.add(link);

  let pubDate;
  try { pubDate = new Date(j.isoDate || j.pubDate || j.date || ''); } catch(_) {}
  // Artikel älter als Cutoff → überspringen
  if (pubDate && !isNaN(pubDate) && (now - pubDate) > cutoffMs) continue;

  fresh.push({
    title:   (j.title || '').replace(/\n/g,' ').replace(/\s+/g,' ').trim(),
    link,
    pubDate: (pubDate && !isNaN(pubDate)) ? pubDate.toISOString() : now.toISOString(),
    summary: (j.contentSnippet || j.summary || j['content:encodedSnippet'] || j.content || '')
               .replace(/<[^>]+>/g,'').replace(/\s+/g,' ').trim().substring(0,300),
    source:  j._source || 'unknown',
  });
}

// Relevanz-Score: Gewichtung nach Inhalt
const HIGH   = ['openai', 'anthropic', 'google deepmind', 'google gemini', 'meta ai', 'mistral', 'grok', 'xai',
                 'benchmark', 'eval', 'mmlu', 'humaneval', 'swe-bench', 'arena', 'leaderboard',
                 'api', 'release', 'launches', 'veröffentlicht', 'model', 'gpt', 'claude', 'gemini',
                 'llama', 'reasoning', 'multimodal', 'agent', 'regulation', 'regulierung', 'eu ai act',
                 'sicherheitslücke', 'vulnerability', 'breach', 'leaked', 'leak'];
const MEDIUM = ['microsoft', 'nvidia', 'apple', 'amazon', 'samsung', 'startup', 'funding',
                 'raises', 'partnership', 'chip', 'hardware', 'open source', 'github'];
const LOW    = ['school', 'art', 'music', 'artist', 'culture', 'opinion', 'essay',
                 'how to', 'guide', 'tips', 'review', 'hands-on'];

function score(item) {
  const hay = (item.title + ' ' + item.summary).toLowerCase();
  if (LOW.some(k => hay.includes(k)))    return 0;
  if (HIGH.some(k => hay.includes(k)))   return 2;
  if (MEDIUM.some(k => hay.includes(k))) return 1;
  return 1;
}

// Primär: Score (höher = besser), Sekundär: Datum (neuer = besser)
fresh.sort((a, b) => {
  const ds = score(b) - score(a);
  if (ds !== 0) return ds;
  return new Date(b.pubDate) - new Date(a.pubDate);
});
const top = fresh.slice(0, 7);

// Fallback: Nichts wirklich Neues → workflow stoppt still
if (top.length === 0) return [];

const dateStr = now.toLocaleDateString('de-DE', {day:'2-digit', month:'2-digit', year:'numeric'});
const newsText = top.map((item, i) =>
  `${i+1}. ${item.title}\n   ${item.summary ? item.summary.substring(0,200) : '(kein Snippet)'}`
).join('\n\n');

const systemPrompt = `Du bist ein KI-News-Redakteur für WhatsApp. Deine Ausgabe folgt exakt diesem Format:

${header} (${dateStr})

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
- KEIN "[4–6 Bullets]" oder andere Template-Notizen im Output

Für "🔥 Wer gerade vorne ist":
- Schreibe Overall und Coding NUR dann aus, wenn die gelieferten Artikel dafür eine konkrete Grundlage liefern (Benchmark, Release, direkter Vergleich).
- Wenn die Artikel keine belastbare Aussage erlauben, schreibe stattdessen exakt:
  🔥 *Wer gerade vorne ist* — heute keine belastbare Änderung
- KEIN freies Einschätzen aus Modellwissen. KEIN Halluzinieren von Rankings.

Sprache: Deutsch. Keine Erfindungen.

Beispiel-Output:
🌅 *KI News – Morgenupdate* (15.04.2026)

• Anthropic veröffentlicht Claude 4 Opus – schlägt GPT-4o auf MMLU und HumanEval.
• OpenAI o3-mini jetzt in der API – Preissenkung um 80% gegenüber o1.
• EU-KI-Act: Hochrisiko-Systeme müssen ab August registriert sein.
• Google Gemini 2.5 Flash übertrifft GPT-4 Turbo auf Reasoning-Benchmarks.

🔥 *Wer gerade vorne ist*
– Overall: Anthropic mit Claude 4 – bestes Reasoning-Modell aktuell
– Coding: OpenAI o3-mini – schnellste und günstigste Code-Option`;

const userPrompt = `Artikel:\n${newsText}`;

const prompt = { systemPrompt, userPrompt };

return [{
  json: {
    systemPrompt: prompt.systemPrompt,
    userPrompt:   prompt.userPrompt,
    header,
    links:   top.map(i => i.link),
    titles:  top.map(i => i.title),
    sources: top.map(i => i.source),
    count:   top.length,
    dateStr,
  }
}];
"""

# ── Code: Format WhatsApp message (kein staticData mehr) ─────────────────────
FORMAT_CODE = r"""
const groqResp = $input.item.json;
let text = 'Keine News verfügbar';
if (groqResp && groqResp.choices && groqResp.choices[0]) {
  text = groqResp.choices[0].message.content.trim();
}
return { json: { message: text } };
"""

RSS_FEEDS = [
    ("The Verge AI",      "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("TechCrunch AI",     "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("Ars Technica Tech", "https://feeds.arstechnica.com/arstechnica/technology-lab"),
    ("MIT Tech Review",   "https://www.technologyreview.com/feed/"),
    ("OpenAI News",       "https://openai.com/news/rss.xml"),
]

def build():
    nodes = []
    conns = {}

    # ── 1. Schedule Trigger ──────────────────────────────────────────────
    nodes.append({
        "id": "schedule-trigger",
        "name": "Schedule Trigger",
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.2,
        "position": [0, 300],
        "parameters": {
            "rule": {"interval": [
                {"field": "cronExpression", "expression": "30 6 * * *"},
                {"field": "cronExpression", "expression": "30 15 * * *"},
            ]}
        }
    })

    # ── 2. PostgreSQL: Get Seen URLs (last 7 days) ───────────────────────
    nodes.append({
        "id": "pg-get-seen",
        "name": "Get Seen URLs",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.5,
        "position": [260, 520],
        "credentials": {"postgres": {"id": PG_CRED, "name": "n8n-postgres (ki_news)"}},
        "parameters": {
            "operation": "executeQuery",
            "query": "SELECT url FROM ki_news_seen WHERE sent_at > NOW() - INTERVAL '7 days';",
            "options": {}
        },
        "onError": "continueRegularOutput",
    })
    conns["Schedule Trigger"] = {"main": [[{"node": "Get Seen URLs", "type": "main", "index": 0}]]}

    # ── 3. RSS Feed nodes (fan-out from Get Seen URLs) ───────────────────
    RSS_X = 540
    n = len(RSS_FEEDS)
    for i, (name, url) in enumerate(RSS_FEEDS):
        y = 60 + i * 120
        nodes.append({
            "id": uid(),
            "name": name,
            "type": "n8n-nodes-base.rssFeedRead",
            "typeVersion": 1,
            "position": [RSS_X, y],
            "parameters": {"url": url},
            "onError": "continueRegularOutput",
        })
        # Get Seen URLs → each RSS node (pass-through – RSS node ignores input)
        conns.setdefault("Get Seen URLs", {"main": [[]]})
        conns["Get Seen URLs"]["main"][0].append({"node": name, "type": "main", "index": 0})

    # ── 4. Merge RSS Feeds ───────────────────────────────────────────────
    nodes.append({
        "id": "merge-rss",
        "name": "Merge RSS Feeds",
        "type": "n8n-nodes-base.merge",
        "typeVersion": 3,
        "position": [820, 300],
        "parameters": {"mode": "append", "options": {}}
    })
    for i, (name, _) in enumerate(RSS_FEEDS):
        conns[name] = {"main": [[{"node": "Merge RSS Feeds", "type": "main", "index": i}]]}

    # ── 5. Merge RSS + PG Seen (append so Code node sees both) ──────────
    nodes.append({
        "id": "merge-all",
        "name": "Merge All",
        "type": "n8n-nodes-base.merge",
        "typeVersion": 3,
        "position": [1060, 300],
        "parameters": {"mode": "append", "options": {}}
    })
    # RSS → Merge All input 0
    conns["Merge RSS Feeds"] = {"main": [[{"node": "Merge All", "type": "main", "index": 0}]]}
    # Get Seen URLs → Merge All input 1  (direct connection from PG node)
    conns["Get Seen URLs"]["main"].append([{"node": "Merge All", "type": "main", "index": 1}])

    # ── 6. Code: Filter & Dedupe ─────────────────────────────────────────
    nodes.append({
        "id": uid(),
        "name": "Filter & Dedupe",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1300, 300],
        "parameters": {
            "mode": "runOnceForAllItems",
            "jsCode": FILTER_CODE.strip(),
        }
    })
    conns["Merge All"] = {"main": [[{"node": "Filter & Dedupe", "type": "main", "index": 0}]]}

    # ── 7. HTTP Request: Groq ────────────────────────────────────────────
    groq_body = (
        '={"model":"llama-3.3-70b-versatile","temperature":0.1,"max_tokens":500,'
        '"messages":['
        '{"role":"system","content":{{ JSON.stringify($json.systemPrompt) }}},'
        '{"role":"user","content":{{ JSON.stringify($json.userPrompt) }}}'
        ']}'
    )
    nodes.append({
        "id": uid(),
        "name": "Groq Summarize",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1560, 300],
        "parameters": {
            "method": "POST",
            "url": "https://api.groq.com/openai/v1/chat/completions",
            "sendHeaders": True,
            "headerParameters": {"parameters": [
                {"name": "Authorization", "value": f"Bearer {GROQ_KEY}"},
                {"name": "Content-Type",  "value": "application/json"},
            ]},
            "sendBody": True, "specifyBody": "json", "jsonBody": groq_body,
            "options": {}
        }
    })
    conns["Filter & Dedupe"] = {"main": [[{"node": "Groq Summarize", "type": "main", "index": 0}]]}

    # ── 8. Code: Format ──────────────────────────────────────────────────
    nodes.append({
        "id": uid(),
        "name": "Format Message",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1820, 300],
        "parameters": {
            "mode": "runOnceForEachItem",
            "jsCode": FORMAT_CODE.strip(),
        }
    })
    conns["Groq Summarize"] = {"main": [[{"node": "Format Message", "type": "main", "index": 0}]]}

    # ── 9. HTTP Request: Telegram ────────────────────────────────────────
    tg_body = '={ "chat_id": "' + TG_CHAT + '", "text": {{ JSON.stringify($json.message) }}, "parse_mode": "Markdown" }'
    nodes.append({
        "id": uid(),
        "name": "Send Telegram",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [2080, 300],
        "parameters": {
            "method": "POST",
            "url": f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            "sendHeaders": True,
            "headerParameters": {"parameters": [
                {"name": "Content-Type", "value": "application/json"},
            ]},
            "sendBody": True, "specifyBody": "json", "jsonBody": tg_body,
            "options": {}
        }
    })
    conns["Format Message"] = {"main": [[{"node": "Send Telegram", "type": "main", "index": 0}]]}

    # ── 10. PostgreSQL: Save Seen URLs ───────────────────────────────────
    # Uses a Code node to build INSERT items, then PG node to insert
    nodes.append({
        "id": uid(),
        "name": "Prepare Insert",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [2340, 300],
        "parameters": {
            "mode": "runOnceForAllItems",
            "jsCode": r"""
// Pull links/titles/sources directly from Filter & Dedupe node
let links = [], titles = [], sources = [];
try {
  const filterItems = $('Filter & Dedupe').all();
  if (filterItems.length > 0) {
    const f = filterItems[0].json;
    links   = f.links   || [];
    titles  = f.titles  || [];
    sources = f.sources || [];
  }
} catch(_) {}

// Return one item per link for bulk INSERT
return links.map((link, i) => ({
  json: {
    url:    link,
    title:  titles[i]  || '',
    source: sources[i] || '',
  }
}));
""".strip()
        }
    })
    conns["Send Telegram"] = {"main": [[{"node": "Prepare Insert", "type": "main", "index": 0}]]}

    nodes.append({
        "id": "pg-save-seen",
        "name": "Save Seen URLs",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.5,
        "position": [2600, 300],
        "credentials": {"postgres": {"id": PG_CRED, "name": "n8n-postgres (ki_news)"}},
        "parameters": {
            "operation": "insert",
            "schema":    {"__rl": True, "value": "public", "mode": "list"},
            "table":     {"__rl": True, "value": "ki_news_seen", "mode": "list"},
            "columns": {
                "mappingMode": "defineBelow",
                "value": {
                    "url":    "={{ $json.url }}",
                    "title":  "={{ $json.title }}",
                    "source": "={{ $json.source }}",
                },
                "matchingColumns": ["url"],
                "schema": [
                    {"id": "url",    "displayName": "url",    "required": False, "defaultMatch": False, "display": True, "type": "string", "canBeUsedToMatch": True},
                    {"id": "title",  "displayName": "title",  "required": False, "defaultMatch": False, "display": True, "type": "string", "canBeUsedToMatch": False},
                    {"id": "source", "displayName": "source", "required": False, "defaultMatch": False, "display": True, "type": "string", "canBeUsedToMatch": False},
                ]
            },
            "options": {"onConflict": {"action": "ignore"}},
        },
        "onError": "continueRegularOutput",
    })
    conns["Prepare Insert"] = {"main": [[{"node": "Save Seen URLs", "type": "main", "index": 0}]]}

    return nodes, conns

nodes, conns = build()

workflow = {
    "name": "KI News Digest",
    "nodes": nodes,
    "connections": conns,
    "settings": {
        "executionOrder": "v1",
        "saveManualExecutions": True,
        "callerPolicy": "workflowsFromSameOwner",
    },
}

# PUT to update
payload = json.dumps(workflow).encode("utf-8")
req = urllib.request.Request(
    f"{N8N_URL}/api/v1/workflows/{WF_ID}",
    data=payload,
    headers={"X-N8N-API-KEY": JWT_KEY, "Content-Type": "application/json"},
    method="PUT",
)
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.loads(r.read())
        print(f"✅ Workflow aktualisiert: ID={body['id']}, Active={body.get('active')}")
        print(f"   Nodes: {len(body.get('nodes', []))}")
except urllib.error.HTTPError as e:
    print(f"❌ HTTP {e.code}: {e.read().decode()[:600]}")
    sys.exit(1)

# Re-activate
req2 = urllib.request.Request(
    f"{N8N_URL}/api/v1/workflows/{WF_ID}/activate",
    headers={"X-N8N-API-KEY": JWT_KEY, "Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req2, timeout=15) as r:
        d = json.loads(r.read())
        print(f"   Active: {d.get('active')}")
except Exception as e:
    print(f"⚠️  Activate: {e}")
