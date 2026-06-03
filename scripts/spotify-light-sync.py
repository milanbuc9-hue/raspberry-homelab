#!/usr/bin/env python3
"""
Spotify → Nanoleaf Beat-Sync
Nimmt die dominante Farbe des aktuellen Albumcovers und pulst die Lampe im Takt.
Beat-Interval kommt aus dem track.tempo falls verfügbar, sonst 500ms (120 BPM).
"""

import io
import json
import time
import colorsys
import requests
import spotipy
from colorthief import ColorThief
from spotipy.oauth2 import SpotifyOAuth

# ─── Konfiguration ────────────────────────────────────────────────────────────

HA_URL    = "http://localhost:8123"
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

HA_TOKEN = os.environ["HA_TOKEN"]
HA_LIGHT  = "light.licht"
HA_TOGGLE = "input_boolean.spotify_licht_sync"

CONFIG_FILE = "/home/milan/.spotify-sync-config.json"
TOKEN_CACHE = "/home/milan/.spotify-sync-token"
SCOPES      = "user-read-playback-state user-read-currently-playing"

DEFAULT_BPM   = 120       # Fallback wenn kein Tempo bekannt
FLASH_BRI     = 255       # Helligkeit auf dem Beat
BASE_BRI_MULT = 0.45      # Base-Helligkeit = FLASH * this
FADE_SEC      = 0.18      # Fade zurück nach dem Flash
CHECK_INTERVAL = 2.0      # Sekunden zwischen Spotify-Polls

# ─── HA Licht ─────────────────────────────────────────────────────────────────

_HEADERS = {"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"}

def ha_light_available() -> bool:
    try:
        r = requests.get(f"{HA_URL}/api/states/{HA_LIGHT}", headers=_HEADERS, timeout=3)
        return r.json().get("state") not in ("unavailable", "unknown")
    except Exception:
        return False

def ha_toggle_active() -> bool:
    try:
        r = requests.get(f"{HA_URL}/api/states/{HA_TOGGLE}", headers=_HEADERS, timeout=3)
        return r.json().get("state") == "on"
    except Exception:
        return True  # Im Zweifel aktiv lassen

def ha_set(hue, sat, bri, transition=0.0):
    try:
        requests.post(f"{HA_URL}/api/services/light/turn_on", headers=_HEADERS,
                      json={"entity_id": HA_LIGHT, "hs_color": [hue, sat],
                            "brightness": int(bri), "transition": transition}, timeout=3)
    except Exception:
        pass

def ha_warmwhite():
    try:
        requests.post(f"{HA_URL}/api/services/light/turn_on", headers=_HEADERS,
                      json={"entity_id": HA_LIGHT, "color_temp_kelvin": 3000,
                            "brightness": 120, "transition": 3}, timeout=3)
    except Exception:
        pass

# ─── Albumcover → dominante Farbe ────────────────────────────────────────────

def album_to_hs(image_url: str) -> tuple[int, int]:
    """Lädt Albumcover, gibt (hue 0-360, saturation 0-100) zurück."""
    try:
        resp = requests.get(image_url, timeout=5)
        ct = ColorThief(io.BytesIO(resp.content))
        r, g, b = ct.get_color(quality=5)
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        # Wenn Farbe zu grau → nimm Palette-Farbe mit höchster Sättigung
        if s < 0.25:
            palette = ct.get_palette(color_count=4, quality=5)
            best = max(palette, key=lambda c: colorsys.rgb_to_hsv(c[0]/255, c[1]/255, c[2]/255)[1])
            h, s, v = colorsys.rgb_to_hsv(best[0]/255, best[1]/255, best[2]/255)
        return int(h * 360), int(max(s, 0.6) * 100)
    except Exception as e:
        print(f"  Albumcover-Fehler: {e}")
        return 200, 80  # Fallback: Blau

# ─── Beat-Sync Loop ───────────────────────────────────────────────────────────

def get_playback(sp):
    try:
        pb = sp.current_playback()
        if not pb or not pb.get("item"):
            return None
        return pb
    except Exception:
        return None

def run(sp):
    track_id    = None
    hue, sat    = 200, 80
    beat_sec    = 60.0 / DEFAULT_BPM
    was_playing = False
    last_check  = 0.0
    last_beat   = time.monotonic()

    print(f"Beat-Sync gestartet  |  Licht: {HA_LIGHT}  |  Toggle: {HA_TOGGLE}")

    light_ok   = True
    toggle_ok  = True

    while True:
        now = time.monotonic()

        # ── Toggle prüfen ─────────────────────────────────────────────────────
        if not ha_toggle_active():
            if toggle_ok:
                print("⏹  Toggle deaktiviert — Beat-Sync pausiert")
                if was_playing:
                    ha_warmwhite()
                    was_playing = False
                    track_id = None
            toggle_ok = False
            time.sleep(5)
            last_check = time.monotonic()
            continue
        if not toggle_ok:
            print("▶  Toggle aktiviert — Beat-Sync läuft wieder")
        toggle_ok = True

        # ── Lampe erreichbar? (alle 30s prüfen wenn zuletzt ok, sofort wenn nicht) ──
        check_interval = 30 if light_ok else 10
        if now - last_check >= check_interval or not light_ok:
            light_ok = ha_light_available()
            if not light_ok:
                print("⚠  light.licht unavailable — warte...")
                time.sleep(10)
                last_check = time.monotonic()
                continue

        # ── Spotify-Poll ──────────────────────────────────────────────────────
        if now - last_check >= CHECK_INTERVAL:
            pb = get_playback(sp)
            last_check = time.monotonic()

            if not pb or not pb.get("is_playing"):
                if was_playing:
                    print("⏸  Pause → Warmweiß")
                    ha_warmwhite()
                    was_playing = False
                    track_id = None
                    last_beat = time.monotonic()
                time.sleep(2)
                continue

            was_playing = True
            item = pb["item"]
            tid  = item["id"]

            if tid != track_id:
                track_id = tid
                name   = item["name"]
                artist = item["artists"][0]["name"]

                # Albumcover → Farbe
                images = item.get("album", {}).get("images", [])
                img_url = images[1]["url"] if len(images) > 1 else (images[0]["url"] if images else None)
                if img_url:
                    hue, sat = album_to_hs(img_url)

                # Tempo aus track-Metadaten (nicht audio_features)
                # Spotify liefert kein Tempo in /currently-playing, daher Fallback
                beat_sec = 60.0 / DEFAULT_BPM

                print(f"\n♪  {artist} — {name}")
                print(f"   Farbe: H={hue}° S={sat}%  Beat: {60/beat_sec:.0f} BPM")

                ha_set(hue, sat, int(FLASH_BRI * BASE_BRI_MULT), transition=1.5)
                last_beat = time.monotonic()

        if not was_playing:
            time.sleep(0.5)
            continue

        # ── Beat-Flash ────────────────────────────────────────────────────────
        since_last = time.monotonic() - last_beat
        sleep_until_beat = beat_sec - since_last - 0.012  # 12ms API-Vorlauf

        if sleep_until_beat > 0:
            time.sleep(sleep_until_beat)

        # Flash auf Beat
        ha_set(hue, sat, FLASH_BRI, transition=0)
        last_beat = time.monotonic()
        time.sleep(0.04)
        ha_set(hue, sat, int(FLASH_BRI * BASE_BRI_MULT), transition=FADE_SEC)

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    with open(CONFIG_FILE) as f:
        cfg = json.load(f)

    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=cfg["client_id"],
        client_secret=cfg["client_secret"],
        redirect_uri="http://127.0.0.1:9090/callback",
        scope=SCOPES,
        cache_path=TOKEN_CACHE,
        open_browser=False,
    ))

    try:
        run(sp)
    except KeyboardInterrupt:
        print("\nBeendet.")

if __name__ == "__main__":
    main()
