# Homelab-Patch (read-only Bind-Mount via docker-compose.yml)
# Ersetzt: /usr/local/lib/pythonX.Y/site-packages/fido2/client/win_api.py
#
# Grund:
#   fido2 2.2.0 + Python 3.14 auf Linux crasht beim Modul-Import von win_api.py
#   (Zeile: HRESULT = ctypes.HRESULT  ->  AttributeError, da Windows-only).
#   asyncssh 2.22.0 (sk.py) umschliesst den Import nur mit `except ImportError`,
#   faengt also AttributeError NICHT ab -> kompletter `import asyncssh` scheitert
#   -> HACS custom_component `ssh_command` laedt nicht.
#
# Fix:
#   win_api.py ist per Design Windows-only. Dieser Host ist Linux/aarch64.
#   Diese Stub-Datei wirft daher auf Nicht-Windows sauber ImportError,
#   den asyncssh abfaengt (WindowsClient = None) -> asyncssh importiert sauber.
#   Versionsunabhaengig: egal welche fido2-Version, hier kommt immer ImportError.
#
# Persistenz: Als Bind-Mount ueberlebt dieser Patch Container-Recreates/Image-Updates
#   (im Gegensatz zu In-Container-pip-Patches, die beim naechsten Pull verschwinden).
import sys

if not sys.platform.startswith("win"):
    raise ImportError(
        "fido2.client.win_api is Windows-only and disabled by homelab bind-mount patch"
    )

# Auf echtem Windows muesste hier die Originaldatei stehen -> auf diesem Pi nie der Fall.
