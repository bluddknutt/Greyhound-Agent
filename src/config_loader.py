"""
Configuration loader for the Greyhound pipeline.

Loads config.yaml from the project root and merges environment variable
overrides for sensitive values (SMTP credentials, email recipients).

Environment variable overrides:
  SMTP_HOST  → email.smtp_host
  SMTP_PORT  → email.smtp_port
  SMTP_USER  → email.smtp_user  (credentials, never stored in config.yaml)
  SMTP_PASS  → email.smtp_pass  (credentials, never stored in config.yaml)
  EMAIL_TO   → email.to_address
"""

import os
from typing import Any

_DEFAULTS: dict[str, Any] = {
    "scraper": {
        "source": "thedogs.com.au",
        "delay_between_requests": 0.3,
        "max_retries": 3,
        "timeout": 30,
        "user_agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    },
    "scorer": {
        "weights": {
            "speed": 0.25,
            "form": 0.22,
            "box_bias": 0.12,
            "class": 0.10,
            "early_speed": 0.10,
            "consistency": 0.11,
            "track_fitness": 0.10,
        },
        "min_win_prob_threshold": 0.15,
    },
    "email": {
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "from_address": "",
        "to_address": "",
        "smtp_user": "",
        "smtp_pass": "",
    },
    "dashboard": {
        "port": 5000,
        "refresh_interval": 300,
        "dark_theme": True,
    },
    "scheduler": {
        "morning_time": "07:00",
        "evening_time": "16:00",
        "timezone": "Australia/Brisbane",
    },
    "tracking": {
        "bet_amount": 10.0,
        "currency": "AUD",
        "bet_type": "win",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, returning a new dict."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: str = "config.yaml") -> dict[str, Any]:
    """
    Load pipeline configuration from a YAML file, merged over built-in defaults.

    Environment variables override the loaded values for sensitive settings.
    If the YAML file does not exist, built-in defaults are used silently.

    Parameters
    ----------
    path : str
        Path to config.yaml relative to the current working directory.

    Returns
    -------
    dict
        Merged configuration dictionary.
    """
    config = dict(_DEFAULTS)

    # Try to load YAML file
    yaml_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), path)
    if not os.path.isabs(path):
        # Also check relative to cwd
        cwd_path = os.path.join(os.getcwd(), path)
        if os.path.exists(cwd_path):
            yaml_path = cwd_path

    if os.path.exists(yaml_path):
        try:
            import yaml  # PyYAML
            with open(yaml_path, "r", encoding="utf-8") as fh:
                file_config = yaml.safe_load(fh) or {}
            config = _deep_merge(config, file_config)
        except Exception as exc:
            print(f"[config_loader] WARNING: Could not load {yaml_path}: {exc}")
    else:
        print(f"[config_loader] INFO: {path} not found, using defaults.")

    # Apply environment variable overrides
    config = _apply_env_overrides(config)
    return config


def _apply_env_overrides(config: dict[str, Any]) -> dict[str, Any]:
    """Apply environment variable overrides to the config dict."""
    env_map = {
        "SMTP_HOST": ("email", "smtp_host"),
        "SMTP_PORT": ("email", "smtp_port"),
        "SMTP_USER": ("email", "smtp_user"),
        "SMTP_PASS": ("email", "smtp_pass"),
        "EMAIL_TO":  ("email", "to_address"),
    }
    for env_var, (section, key) in env_map.items():
        val = os.environ.get(env_var)
        if val is not None:
            config[section][key] = val

    # SMTP_PORT should be int
    try:
        config["email"]["smtp_port"] = int(config["email"]["smtp_port"])
    except (ValueError, TypeError):
        config["email"]["smtp_port"] = 587

    return config


def get_smtp_config() -> dict[str, Any]:
    """
    Return the email/SMTP section of the config, with credentials from env vars.

    Returns
    -------
    dict with keys: smtp_host, smtp_port, smtp_user, smtp_pass,
                    from_address, to_address
    """
    config = load_config()
    return config["email"]
