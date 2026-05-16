"""
Central configuration loader. All scripts import config from here.
"""
import os
import yaml
from pathlib import Path
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).parent.parent
CONFIG_PATH = REPO_ROOT / "01_pipeline_setup" / "config.yaml"
ENV_PATH = REPO_ROOT / "01_pipeline_setup" / ".env"
DATA_DIR = REPO_ROOT / "data"

load_dotenv(ENV_PATH)


def load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def get_env(key: str, required: bool = True) -> str:
    val = os.getenv(key, "")
    if required and not val:
        raise EnvironmentError(f"Missing required env var: {key}. Set it in {ENV_PATH}")
    return val


def ensure_data_dirs():
    """Create standard data output directories."""
    for sub in ["probe", "scraped", "chunks", "embeddings"]:
        (DATA_DIR / sub).mkdir(parents=True, exist_ok=True)
    return DATA_DIR
