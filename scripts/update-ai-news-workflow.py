#!/usr/bin/env python3
"""Aktualisiert den KI-News-Digest Workflow mit korrekter Konfiguration."""

import json
import uuid
import urllib.request
import urllib.error
import sys

N8N_URL    = "http://milan:5678"
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
EVOL_KEY = os.environ["EVOLUTION_API_KEY"]
WA_INST    = "milan-whatsapp"
WA_NUMBER = os.environ["WHATSAPP_NUMBER"]
WF_ID      = open("/home/milan/scripts/.ai-news-workflow-id").read().strip()

def uid():
    return str(uuid.uuid4())

FILTER_CODE = r"""
const allItems = $input.all();
const staticData = $getWorkflowStaticData('global');
if (!staticData.seenUrls) staticData.seenUrls = [];
const alreadySeen = new Set(staticData.seenUrls);

const now = new Date();
const utcHour = now.getUTCHours();
const isEvening = utcHour >= 12;
const header = isEvening
  ? '🌆 *KI News – Abendupdate*'
  : '🌅 *KI News – Morgenupdate*';

const cutoffMs = 13 * 60 * 60 * 1000; // 13h – covers both morning and evening runs

const seenInRun = new Set();
const fresh = [];

for (const item of allItems) {
  const j = item.json;
  const link = (j.link || j.url || '').trim().replace(/\?.*$/, '').replace(/#.*$/, '');
  if (!link) continue;
  if (alreadySeen.has(link)) continue;
  if (seenInRun.has(link)) continue;
  seenInRun.add(link);

  let pubDate;
  try { pubDate = new Date(j.isoDate || j.pubDate || j.date || ''); } catch(_) {}
  if (pubDate && !isNaN(pubDate) && (now - pubDate) > cutoffMs) continue;

  fresh.push({
    title:   (j.title || '').replace(/\n/g, ' ').replace(/\s+/g,' ').trim(),
    link,
    pubDate: pubDate && !isNaN(pubDate) ? pubDate.toISOString() : now.toISOString(),
    summary: (j.contentSnippet || j.summary || j['content:encodedSnippet'] || j.content || '')
               .replace(/<[^>]+>/g, '').replace(/\s+/g,' ').trim().substring(0, 300),
  });
}

fresh.sort((a, b) => new Date(b.pubDate) - new Date(a.pubDate));
const top = fresh.slice(0, 7);

if (top.length === 0) return [];

const dateStr = now.toLocaleDateString('de-DE', {day:'2-digit', month:'2-digit', year:'numeric'});
const newsText = top.map((item, i) =>
  `${i+1}. ${item.title}\n   ${item.summary ? item.summary.substring(0, 200) : '(kein Snippet)'}`
).join('\n\n');

const prompt = `Du bist ein präziser KI-News-Kurator für WhatsApp-Nachrichten.

Fasse NUR diese ${top.length} Artikel zusammen – erfinde nichts.

GEWÜNSCHTES FORMAT:
${header} (${dateStr})

• [Was ist passiert + warum wichtig – max. 2 Sätze pro Punkt]
• ...
[4–6 Punkte total, nur wirklich KI-relevante Meldungen]

REGELN:
- Nur Punkte für: Modellreleases, API-Updates, Benchmarks, Regulierung, Partnerschaften, Sicherheitsthemen, relevante Produktankündigungen
- Keine Punkte für reine Businessnews ohne KI-Bezug
- Kein Clickbait, keine erfundenen Details
- Kein abschließendes Gelaber
- Kompakt, klar, auf Deutsch

ARTIKEL:
${newsText}`;

return [{
  json: {
    prompt,
    header,
    links: top.map(i => i.link),
    count: top.length,
    dateStr,
  }
}];
"""

FORMAT_CODE = r"""
const groqResp = $input.item.json;

let text = '';
try {
  text = groqResp.choices[0].message.content.trim();
} catch(e) {
  return [{ json: { error: 'Groq parse failed', raw: JSON.stringify(groqResp).substring(0,200) } }];
}

// Save seen URLs
const staticData = $getWorkflowStaticData('global');
if (!staticData.seenUrls) staticData.seenUrls = [];

let links = [];
try { links = $('Filter & Dedupe').item.json.links || []; } catch(_) {}

for (const link of links) {
  if (!staticData.seenUrls.includes(link)) {
    staticData.seenUrls.push(link);
  }
}
if (staticData.seenUrls.length > 600) {
  staticData.seenUrls = staticData.seenUrls.slice(-600);
}

return [{ json: { message: text } }];
"""

RSS_FEEDS = [
    ("The Verge AI",      "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("TechCrunch AI",     "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("Ars Technica Tech", "https://feeds.arstechnica.com/arstechnica/technology-lab"),
    ("MIT Tech Review",   "https://www.technologyreview.com/feed/"),
    ("OpenAI News",       "https://openai.com/news/rss.xml"),
]

def make_nodes():
    nodes = []
    connections = {}

    # 1. Schedule Trigger
    nodes.append({
        "id": "schedule-trigger",
        "name": "Schedule Trigger",
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.2,
        "position": [0, 300],
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
    RSS_X, MERGE_X = 260, 560
    n = len(RSS_FEEDS)
    for i, (name, url) in enumerate(RSS_FEEDS):
        y = 300 - ((n-1)*120//2) + i*120
        nid = uid()
        nodes.append({
            "id": nid,
            "name": name,
            "type": "n8n-nodes-base.rssFeedRead",
            "typeVersion": 1,
            "position": [RSS_X, y],
            "parameters": {"url": url},
            "onError": "continueRegularOutput",
        })
        connections.setdefault("Schedule Trigger", {"main": [[]]})
        connections["Schedule Trigger"]["main"][0].append({"node": name, "type": "main", "index": 0})

    # 3. Merge
    mid = uid()
    nodes.append({
        "id": mid,
        "name": "Merge Feeds",
        "type": "n8n-nodes-base.merge",
        "typeVersion": 3,
        "position": [MERGE_X, 300],
        "parameters": {"mode": "append", "options": {}}
    })
    for i, (name, _) in enumerate(RSS_FEEDS):
        connections[name] = {"main": [[{"node": "Merge Feeds", "type": "main", "index": i}]]}

    # 4. Code: Filter & Dedupe
    fid = uid()
    nodes.append({
        "id": fid,
        "name": "Filter & Dedupe",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [820, 300],
        "parameters": {
            "mode": "runOnceForAllItems",
            "jsCode": FILTER_CODE.strip(),
        }
    })
    connections["Merge Feeds"] = {"main": [[{"node": "Filter & Dedupe", "type": "main", "index": 0}]]}

    # 5. HTTP Request: Groq
    gid = uid()
    # Build the JSON body expression exactly like the existing workflow
    groq_body = (
        '={"model":"llama-3.3-70b-versatile","temperature":0.3,"max_tokens":700,'
        '"messages":[{"role":"user","content":' + '{{ JSON.stringify($json.prompt) }}' + '}]}'
    )
    nodes.append({
        "id": gid,
        "name": "Groq Summarize",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1080, 300],
        "parameters": {
            "method": "POST",
            "url": "https://api.groq.com/openai/v1/chat/completions",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Authorization", "value": f"Bearer {GROQ_KEY}"},
                    {"name": "Content-Type",  "value": "application/json"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": groq_body,
            "options": {}
        }
    })
    connections["Filter & Dedupe"] = {"main": [[{"node": "Groq Summarize", "type": "main", "index": 0}]]}

    # 6. Code: Format + Save Seen
    fmid = uid()
    nodes.append({
        "id": fmid,
        "name": "Format & Save Seen",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1340, 300],
        "parameters": {
            "mode": "runOnceForEachItem",
            "jsCode": FORMAT_CODE.strip(),
        }
    })
    connections["Groq Summarize"] = {"main": [[{"node": "Format & Save Seen", "type": "main", "index": 0}]]}

    # 7. HTTP Request: WhatsApp
    wid = uid()
    # Use same pattern as existing working WhatsApp workflow
    wa_body = '={ "number": "' + WA_NUMBER + '", "text": {{ $json.message }} }'
    nodes.append({
        "id": wid,
        "name": "Send WhatsApp",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1600, 300],
        "parameters": {
            "method": "POST",
            "url": f"http://evolution-api:8080/message/sendText/{WA_INST}",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "apikey",       "value": EVOL_KEY},
                    {"name": "Content-Type", "value": "application/json"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": wa_body,
            "options": {}
        }
    })
    connections["Format & Save Seen"] = {"main": [[{"node": "Send WhatsApp", "type": "main", "index": 0}]]}

    return nodes, connections


nodes, connections = make_nodes()

workflow_update = {
    "name": "KI News Digest",
    "nodes": nodes,
    "connections": connections,
    "settings": {
        "executionOrder": "v1",
        "saveManualExecutions": True,
        "callerPolicy": "workflowsFromSameOwner",
    },
}

payload = json.dumps(workflow_update).encode("utf-8")
req = urllib.request.Request(
    f"{N8N_URL}/api/v1/workflows/{WF_ID}",
    data=payload,
    headers={
        "X-N8N-API-KEY": JWT_KEY,
        "Content-Type": "application/json",
    },
    method="PUT",
)

try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read())
        print(f"✅ Workflow aktualisiert: ID={body['id']}, Active={body.get('active')}")
except urllib.error.HTTPError as e:
    err = e.read().decode()
    print(f"❌ HTTP {e.code}: {err[:500]}")
    sys.exit(1)
