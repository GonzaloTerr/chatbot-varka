"""Configuracion central: lee todo de variables de entorno.
Sin claves hardcodeadas (las carga EasyPanel en produccion, o el .env en local)."""
import os

from dotenv import load_dotenv

load_dotenv()  # carga el .env en local; en EasyPanel no hay .env y usa las vars del panel

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

# --- WhatsApp Cloud API (Meta) — transporte actual ---
GRAPH_API_VERSION = os.environ.get("GRAPH_API_VERSION", "v22.0")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN", "")               # token de acceso (permanente en prod)
WHATSAPP_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")  # id del numero (no el numero)
WHATSAPP_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "varka_wa_2026")  # para el GET de verificacion

# --- WAHA (legacy, ya no se usa; se migro a la Cloud API oficial) ---
WAHA_URL = os.environ.get("WAHA_URL", "https://your-waha-host.example.com")
WAHA_API_KEY = os.environ.get("WAHA_API_KEY", "")
WAHA_SESSION = os.environ.get("WAHA_SESSION", "default")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://your-project.supabase.co")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# --- RAG: embeddings con Voyage AI + Supabase pgvector ---
VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY", "")
MODEL_EMBED = os.environ.get("MODEL_EMBED", "voyage-3.5-lite")  # 1024 dimensiones
CAL_LINK = os.environ.get("CAL_LINK", "https://cal.com/consultora-varka/diagnostico-gratuito")
MODEL = os.environ.get("MODEL", "claude-haiku-4-5")

# Cal.com (para que Sofia reserve turnos sola)
CAL_API_KEY = os.environ.get("CAL_API_KEY", "")
CAL_EVENT_TYPE_ID = os.environ.get("CAL_EVENT_TYPE_ID", "")  # lo completamos juntos
TIMEZONE = os.environ.get("TIMEZONE", "America/Argentina/Buenos_Aires")
