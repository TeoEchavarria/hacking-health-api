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
            "mobile": {"version": "1.0.0", "url": "https://github.com/2wiks/ss0-web-health-tech/blob/main/public/downloads/hh_1_0_0.apk"},
            "watch": {"version": "1.0.0", "url": "https://github.com/2wiks/ss0-web-health-tech/blob/main/public/downloads/hh_watch_1_0_0.apk"}
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
