"""Configuracion central: lee todo de variables de entorno.
Sin claves hardcodeadas (las carga EasyPanel en produccion, o el .env en local)."""
import os

from dotenv import load_dotenv

load_dotenv()  # carga el .env en local; en EasyPanel no hay .env y usa las vars del panel

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

WAHA_URL = os.environ.get("WAHA_URL", "https://your-waha-host.example.com")
WAHA_API_KEY = os.environ.get("WAHA_API_KEY", "")
WAHA_SESSION = os.environ.get("WAHA_SESSION", "default")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://your-project.supabase.co")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
CAL_LINK = os.environ.get("CAL_LINK", "https://cal.com/consultora-varka/diagnostico-gratuito")
MODEL = os.environ.get("MODEL", "claude-haiku-4-5")

# Cal.com (para que Sofia reserve turnos sola)
CAL_API_KEY = os.environ.get("CAL_API_KEY", "")
CAL_EVENT_TYPE_ID = os.environ.get("CAL_EVENT_TYPE_ID", "")  # lo completamos juntos
TIMEZONE = os.environ.get("TIMEZONE", "America/Argentina/Buenos_Aires")
