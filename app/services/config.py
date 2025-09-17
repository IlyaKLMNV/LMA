# Centralized settings and model-profile resolver.

import os
from typing import Any, Dict, Optional
import yaml
from dotenv import load_dotenv

load_dotenv()  # load .env from project root

# Read Mistral API key (support both env names to avoid breaking existing .env)
MISTRAL_API_KEY = os.getenv("LMA_MISTRAL_API_KEY") or os.getenv("MISTRAL_API_KEY")
if not MISTRAL_API_KEY:
    raise RuntimeError("Missing LMA_MISTRAL_API_KEY (or MISTRAL_API_KEY) in .env")

MISTRAL_BASE = "https://api.mistral.ai/v1"
EMBED_MODEL = os.getenv("EMBED_MODEL", "mistral-embed")

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", None)
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "kb")

MODELS_CONFIG_PATH = os.getenv("MODELS_CONFIG_PATH", "configs/models.yaml")

DEFAULT_PROFILE: Dict[str, Any] = {
    "provider": "mistral",
    "model": "open-mistral-7b",
    "temperature": 0.3,
    "max_tokens": 512,
}

def load_models_config(path: str) -> Dict[str, Any]:
    """Load YAML config for model profiles; provide a safe fallback."""
    if not os.path.exists(path):
        return {"models": {"default": "chat-general", "chat-general": DEFAULT_PROFILE}}
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    if "models" not in cfg or "default" not in cfg["models"]:
        raise RuntimeError("models.yaml must include 'models.default' and at least one profile.")
    return cfg

MODELS_CFG = load_models_config(MODELS_CONFIG_PATH)

def resolve_profile(name: Optional[str]) -> Dict[str, Any]:
    """Return selected profile dict."""
    models = MODELS_CFG["models"]
    use = name or models["default"]
    if use not in models:
        raise ValueError(f"Unknown profile '{use}'. Available: {', '.join(k for k in models if k!='default')}")
    return models[use]

def pick_model_and_params(
    profile_name: Optional[str],
    explicit_model: Optional[str],
    explicit_temp: Optional[float],
    explicit_max_tokens: Optional[int],
) -> Dict[str, Any]:
    """Resolve final model and params honoring profile+overrides."""
    prof = resolve_profile(profile_name)
    if prof.get("provider") != "mistral":
        raise ValueError("Only 'mistral' provider is implemented in this API version.")
    model = explicit_model or prof["model"]
    temperature = explicit_temp if explicit_temp is not None else prof.get("temperature", 0.3)
    max_tokens = explicit_max_tokens if explicit_max_tokens is not None else prof.get("max_tokens", 512)
    return {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "profile": profile_name or MODELS_CFG["models"]["default"],
    }
