import os

# In production, set these as environment variables instead of using the defaults.
SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-secret-key-change-me-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./finance.db")
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
# Also allow the frontend from localhost or 127.0.0.1 on any port (Vite picks 5174, 5175... when 5173 is busy).
# Set CORS_ORIGIN_REGEX to an empty value in production to allow only CORS_ORIGINS.
CORS_ORIGIN_REGEX = os.getenv("CORS_ORIGIN_REGEX", r"http://(localhost|127\.0\.0\.1)(:\d+)?") or None

# AI features run on a local Ollama server (https://ollama.com), so no API key and no data leaves your computer.
# Without Ollama running, auto-categorize and insights fall back to built-in rules and the assistant explains how
# to start it.
AI_ENABLED = os.getenv("AI_ENABLED", "true").lower() not in ("0", "false", "no", "off")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "180"))  # seconds; the first answer loads the model into memory
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "8192"))  # context window in tokens
