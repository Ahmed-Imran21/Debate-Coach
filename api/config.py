import os
import re

from dotenv import load_dotenv

from .models import APIKey, APILimits
from .key_registry import APIKeyRegistry


# Load values from .env
load_dotenv()


# ---------------------------------------------------------
# Supported provider/model configurations
# ---------------------------------------------------------

KEY_CONFIGS = {
    "GROQ_GPT_OSS_120B": {
        "provider": "groq",
        "model": "openai/gpt-oss-120b",
        "limits": APILimits(
            rpm=30,
            rpd=1000,
            tpm=8000,
            tpd=200000,
        ),
    },

    "GROQ_LLAMA_3_3_70B": {
        "provider": "groq",
        "model": "llama-3.3-70b-versatile",
        "limits": APILimits(
            rpm=30,
            rpd=1000,
            tpm=12000,
            tpd=100000,
        ),
    },

    "GEMINI_2_5_FLASH": {
        "provider": "gemini",
        "model": "gemini-2.5-flash",
        "limits": APILimits(
            rpm=15,
            rpd=1500,
            tpm=250000,
            tpd=1000000,
        ),
    },
}


# ---------------------------------------------------------
# Key loader
# ---------------------------------------------------------

def load_api_keys() -> list[APIKey]:
    """
    Automatically discover all API keys defined in .env.

    Example:

        GROQ_GPT_OSS_120B_KEY_1=...
        GROQ_GPT_OSS_120B_KEY_2=...
        GROQ_GPT_OSS_120B_KEY_3=...

    Adding KEY_4 requires no code changes.
    """

    api_keys = []

    for config_name, config in KEY_CONFIGS.items():

        pattern = re.compile(
            rf"^{re.escape(config_name)}_KEY_(\d+)$"
        )

        for env_name, env_value in os.environ.items():

            match = pattern.match(env_name)

            if not match:
                continue

            # Ignore empty variables
            if not env_value:
                continue

            key_number = match.group(1)

            api_key = APIKey(
                id=f"{config_name.lower()}_{key_number}",
                provider=config["provider"],
                model=config["model"],
                key=env_value,
                limits=config["limits"],
            )

            api_keys.append(api_key)

    return api_keys


# ---------------------------------------------------------
# Registry builder
# ---------------------------------------------------------

def build_registry() -> APIKeyRegistry:
    """
    Load all API keys and place them into the central registry.
    """

    registry = APIKeyRegistry()

    api_keys = load_api_keys()

    if not api_keys:
        raise RuntimeError(
            "No API keys were found. "
            "Check your .env file."
        )

    for api_key in api_keys:
        registry.add_key(api_key)

    return registry


# ---------------------------------------------------------
# Configuration information
# ---------------------------------------------------------

def get_loaded_key_count() -> int:
    """
    Return the number of API keys discovered in .env.
    """

    return len(load_api_keys())


def print_loaded_keys() -> None:
    """
    Print loaded keys without exposing the actual secret values.
    """

    api_keys = load_api_keys()

    print(f"Loaded {len(api_keys)} API keys:")

    for api_key in api_keys:
        print(
            f"  {api_key.id} | "
            f"{api_key.provider} | "
            f"{api_key.model}"
        )