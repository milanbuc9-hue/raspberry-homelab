#!/usr/bin/env python3
"""Erstellt den KI-News-Digest Workflow in n8n via API."""

import json
import uuid
import urllib.request
import urllib.error
import sys

N8N_URL = "http://milan:5678"
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
GROQ_API_KEY = os.environ["GROQ_API_KEY"]
WA_API_KEY = os.environ["WHATSAPP_API_KEY"]
WA_INSTANCE  = "milan-whatsapp"
WA_NUMBER = os.environ["WHATSAPP_NUMBER"]

def uid():
    return str(uuid.uuid4())

# ── Code: Filter, Dedupe, Build Prompt ──────────────────────────────────────
FILTER_CODE = r"""
const allItems = $input.all();
const staticData = $getWorkflowStaticData('global');
if (!staticData.seenUrls) staticData.seenUrls = [];
const seen = new Set(staticData.seenUrls);

const now = new Date();
// 08:30 CEST = 06:30 UTC -> morning; 17:30 CEST = 15:30 UTC -> evening
const utcHour = now.getUTCHours();
const isEvening = utcHour >= 12;
const header = isEvening
  ? '🌆 *KI News – Abendupdate*'
  : '🌅 *KI News – Morgenupdate*';

const cutoffMs = 13 * 60 * 60 * 1000; // 13h window covers both runs

const fresh = [];
for (const item of allItems) {
  const j = item.json;
  const link = (j.link || j.url || '').trim();
  if (!link) continue;
  if (seen.has(link)) continue;

  let pubDate;
  try { pubDate = new Date(j.isoDate || j.pubDate || j.date || ''); } catch(_) {}
  if (pubDate && !isNaN(pubDate) && (now - pubDate) > cutoffMs) continue;

  // dedup by link within this run
  seen.add(link);

  fresh.push({
    title:   (j.title || '').replace(/\n/g, ' ').trim(),
    link,
    pubDate: pubDate && !isNaN(pubDate) ? pubDate.toISOString() : new Date().toISOString(),
    summary: (j.contentSnippet || j.summary || j.content || '').replace(/<[^>]+>/g, '').substring(0, 250).trim(),
  });
}

// Sort newest first
fresh.sort((a, b) => new Date(b.pubDate) - new Date(a.pubDate));

// Top 7
const top = fresh.slice(0, 7);

if (top.length === 0) {
  return [];
}

const newsText = top.map((item, i) =>
  `${i+1}. ${item.title}\n   ${item.summary ? item.summary.substring(0, 180) : ''}`
).join('\n\n');

const dateStr = now.toLocaleDateString('de-DE', {day:'2-digit', month:'2-digit', year:'numeric'});

const prompt = `Du bist ein präziser KI-News-Kurator für WhatsApp.

Fasse NUR die folgenden ${top.length} echten Artikel zusammen. Erfinde nichts.

FORMAT (exakt so):
${header} (${dateStr})

• [Was passiert + warum wichtig – max. 2 Sätze]
• [Was passiert + warum wichtig – max. 2 Sätze]
[... 4-6 Punkte total, nur wenn wirklich relevant]

REGELN:
- Nur Punkte für KI-relevante News: Modellreleases, APIs, Benchmarks, Regulierung, Firmen-Ankündigungen, Sicherheit
- Kein Clickbait, keine erfundenen Details
- Kein abschließendes Gelaber ("Bleib informiert" etc.)
- Kompakt, klar, auf Deutsch
- Wenn weniger als 4 relevante Artikel: weniger Punkte, kein Auffüllen

ARTIKEL:
${newsText}`;

return [{
  json: {
    prompt,
    header,
    links: top.map(i => i.link),
    count: top.length,
  }
}];
"""

# ── Code: Format WhatsApp + Save Seen URLs ───────────────────────────────────
FORMAT_CODE = r"""
const groqResp = $input.item.json;

// Extract text from Groq response
let text = '';
try {
  text = groqResp.choices[0].message.content.trim();
} catch(e) {
  return [{ json: { error: 'Groq response parse failed', raw: JSON.stringify(groqResp) } }];
}

// Save seen URLs to static data
const staticData = $getWorkflowStaticData('global');
if (!staticData.seenUrls) staticData.seenUrls = [];

let links = [];
try {
  links = $('Filter & Dedupe').item.json.links || [];
} catch(_) {}

for (const link of links) {
  if (!staticData.seenUrls.includes(link)) {
    staticData.seenUrls.push(link);
  }
}
// Keep max 500 URLs to avoid unbounded growth
if (staticData.seenUrls.length > 500) {
  staticData.seenUrls = staticData.seenUrls.slice(-500);
}

return [{ json: { message: text } }];
"""

# ── Workflow JSON ─────────────────────────────────────────────────────────────
RSS_FEEDS = [
    ("The Verge AI",        "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("VentureBeat AI",      "https://venturebeat.com/ai/feed/"),
    ("TechCrunch AI",       "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("Ars Technica Tech",   "https://feeds.arstechnica.com/arstechnica/technology-lab"),
    ("MIT Tech Review",     "https://www.technologyreview.com/feed/"),
]

# Node positions
POS_TRIGGER     = [0,    300]
POS_RSS_BASE_X  = 260
POS_MERGE       = [560,  300]
POS_FILTER      = [800,  300]
POS_GROQ        = [1060, 300]
POS_FORMAT      = [1320, 300]
POS_WA          = [1580, 300]

def rss_y(i):
    total = len(RSS_FEEDS)
    step = 120
    start = 300 - ((total-1) * step // 2)
    return start + i * step

nodes = []
connections = {}

# 1. Schedule Trigger
trigger_id = "schedule-trigger"
nodes.append({
    "id": trigger_id,
    "name": "Schedule Trigger",
    "type": "n8n-nodes-base.scheduleTrigger",
    "typeVersion": 1.2,
    "position": POS_TRIGGER,
    "parameters": {
        "rule": {
            "interval": [
                {"field": "cronExpression", "expression": "30 6 * * *"},
                {"field": "cronExpression", "expression": "30 15 * * *"},
            ]
        }
    }
})

# 2. RSS Feed nodes
rss_ids = []
for i, (name, url) in enumerate(RSS_FEEDS):
    nid = uid()
    rss_ids.append(nid)
    nodes.append({
        "id": nid,
        "name": name,
        "type": "n8n-nodes-base.rssFeedRead",
        "typeVersion": 1,
        "position": [POS_RSS_BASE_X, rss_y(i)],
        "parameters": {"url": url},
    })
    # Schedule Trigger → each RSS node
    connections.setdefault("Schedule Trigger", {"main": [[]]})
    connections["Schedule Trigger"]["main"][0].append({"node": name, "type": "main", "index": 0})

# 3. Merge node
merge_id = uid()
nodes.append({
    "id": merge_id,
    "name": "Merge Feeds",
    "type": "n8n-nodes-base.merge",
    "typeVersion": 3,
    "position": POS_MERGE,
    "parameters": {
        "mode": "append",
        "options": {}
    }
})
# Each RSS → Merge (different input index)
for i, (name, _) in enumerate(RSS_FEEDS):
    connections[name] = {"main": [[{"node": "Merge Feeds", "type": "main", "index": i}]]}

# 4. Code: Filter & Dedupe
filter_id = uid()
nodes.append({
    "id": filter_id,
    "name": "Filter & Dedupe",
    "type": "n8n-nodes-base.code",
    "typeVersion": 2,
    "position": POS_FILTER,
    "parameters": {
        "mode": "runOnceForAllItems",
        "jsCode": FILTER_CODE.strip(),
    }
})
connections["Merge Feeds"] = {"main": [[{"node": "Filter & Dedupe", "type": "main", "index": 0}]]}

# 5. HTTP Request: Groq API
groq_body = json.dumps({
    "model": "llama-3.3-70b-versatile",
    "temperature": 0.3,
    "max_tokens": 600,
    "messages": [{"role": "user", "content": "={{ $json.prompt }}"}]
})
groq_id = uid()
nodes.append({
    "id": groq_id,
    "name": "Groq Summarize",
    "type": "n8n-nodes-base.httpRequest",
    "typeVersion": 4.2,
    "position": POS_GROQ,
    "parameters": {
        "method": "POST",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "sendHeaders": True,
        "headerParameters": {
            "parameters": [
                {"name": "Authorization", "value": f"Bearer {GROQ_API_KEY}"},
                {"name": "Content-Type",  "value": "application/json"},
            ]
        },
        "sendBody": True,
        "specifyBody": "string",
        "body": "={ \"model\": \"llama-3.3-70b-versatile\", \"temperature\": 0.3, \"max_tokens\": 600, \"messages\": [{ \"role\": \"user\", \"content\": {{ JSON.stringify($json.prompt) }} }] }",
        "options": {}
    }
})
connections["Filter & Dedupe"] = {"main": [[{"node": "Groq Summarize", "type": "main", "index": 0}]]}

# 6. Code: Format + Save Seen
format_id = uid()
nodes.append({
    "id": format_id,
    "name": "Format & Save Seen",
    "type": "n8n-nodes-base.code",
    "typeVersion": 2,
    "position": POS_FORMAT,
    "parameters": {
        "mode": "runOnceForEachItem",
        "jsCode": FORMAT_CODE.strip(),
    }
})
connections["Groq Summarize"] = {"main": [[{"node": "Format & Save Seen", "type": "main", "index": 0}]]}

# 7. HTTP Request: Evolution API WhatsApp
wa_id = uid()
nodes.append({
    "id": wa_id,
    "name": "Send WhatsApp",
    "type": "n8n-nodes-base.httpRequest",
    "typeVersion": 4.2,
    "position": POS_WA,
    "parameters": {
        "method": "POST",
        "url": f"http://evolution-api:8080/message/sendText/{WA_INSTANCE}",
        "sendHeaders": True,
        "headerParameters": {
            "parameters": [
                {"name": "apikey",       "value": WA_API_KEY},
                {"name": "Content-Type", "value": "application/json"},
            ]
        },
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": f"={{{{ {{\"number\": \"{WA_NUMBER}\", \"text\": {{{{ $json.message }}}} }} }}}}",
        "options": {}
    }
})
connections["Format & Save Seen"] = {"main": [[{"node": "Send WhatsApp", "type": "main", "index": 0}]]}

workflow = {
    "name": "KI News Digest",
    "nodes": nodes,
    "connections": connections,
    "settings": {
        "executionOrder": "v1",
        "saveManualExecutions": True,
        "callerPolicy": "workflowsFromSameOwner",
    },
}

# ── POST to n8n API ───────────────────────────────────────────────────────────
payload = json.dumps(workflow).encode("utf-8")
req = urllib.request.Request(
    f"{N8N_URL}/api/v1/workflows",
    data=payload,
    headers={
        "X-N8N-API-KEY": JWT_KEY,
        "Content-Type": "application/json",
    },
    method="POST",
)

try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read())
        print(f"✅ Workflow erstellt: ID={body['id']}, Name={body['name']}, Active={body.get('active')}")
        print(f"   URL: http://milan:5678/workflow/{body['id']}")
        # Write workflow ID to file for reference
        with open("/home/milan/scripts/.ai-news-workflow-id", "w") as f:
            f.write(body["id"])
except urllib.error.HTTPError as e:
    err = e.read().decode()
    print(f"❌ HTTP {e.code}: {err}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
