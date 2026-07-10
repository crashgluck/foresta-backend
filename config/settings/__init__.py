import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BASE_DIR / ".env"
ENV_REAL_FILE = BASE_DIR / ".env.real"

load_dotenv(
    ENV_FILE if ENV_FILE.exists() else ENV_REAL_FILE,
    override=True,
)

env = os.getenv("DJANGO_ENV", "local").strip().lower()

if env == "production":
    from .production import *  # noqa: F401,F403
elif env == "test":
    from .test import *  # noqa: F401,F403
else:
    from .local import *  # noqa: F401,F403