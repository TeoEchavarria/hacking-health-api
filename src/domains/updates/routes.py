import json
import os
from fastapi import APIRouter, HTTPException

router = APIRouter(
    prefix="/app/updates",
    tags=["updates"]
)

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {
            "mobile": {"version": "0.0.0", "url": ""},
            "watch": {"version": "0.0.0", "url": ""}
        }
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {
            "mobile": {"version": "0.0.0", "url": ""},
            "watch": {"version": "0.0.0", "url": ""}
        }

@router.get("")
def get_updates():
    """
    Get the latest version information for mobile and watch apps.
    """
    return load_config()
