import requests
import json
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

# API Endpoints
GAMMA_API_URL = "https://gamma-api.polymarket.com/events/slug"
MARKET_API_URL = "https://gamma-api.polymarket.com/markets/slug"
CLOB_HISTORY_API_URL = "https://clob.polymarket.com/prices-history"

def get_headers():
    return {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }

def parse_stringified_list(data):
    """Parses fields that might be JSON strings (e.g. "['Yes', 'No']")."""
    if isinstance(data, str):
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return []
    return data

def get_event_markets(url):
    """Fetches the event summary from the Event URL."""
    try:
        parsed = urlparse(url)
        path_parts = parsed.path.strip("/").split("/")
        # Extract slug: usually the last part, or the part after 'event'
        slug = path_parts[-1] if "event" not in path_parts else path_parts[path_parts.index("event") + 1]

        print(f"DEBUG: Fetching Event Slug: {slug}")
        response = requests.get(f"{GAMMA_API_URL}/{slug}", headers=get_headers())
        response.raise_for_status()
        data = response.json()
        return data.get('markets', [])
    except Exception as e:
        print(f"Error fetching event: {e}")
        return []

def fetch_full_market_details(market_slug):
    """Fetches detailed market data if the event summary is incomplete."""
    try:
        url = f"{MARKET_API_URL}/{market_slug}"
        response = requests.get(url, headers=get_headers())
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return None

def get_yes_token_id(market):
    """
    Robustly extracts the Token ID for the 'Yes' outcome.
    Checks 'tokens' list first, then falls back to 'clobTokenIds' mapping.
    """
    # 1. Check 'tokens' list (Best source)
    tokens = market.get('tokens')
    if tokens and isinstance(tokens, list):
        for t in tokens:
            if str(t.get('outcome', '')).strip().lower() in ["yes", "true"]:
                return t.get('tokenId')

    # 2. Check 'clobTokenIds' mapping
    outcomes = parse_stringified_list(market.get('outcomes'))
    clob_ids = parse_stringified_list(market.get('clobTokenIds'))
    
    if clob_ids and outcomes:
        try:
            # Find index of "Yes" (case-insensitive)
            idx = -1
            for i, outcome in enumerate(outcomes):
                if str(outcome).strip().lower() in ["yes", "true"]:
                    idx = i
                    break
            
            if idx != -1 and idx < len(clob_ids):
                return clob_ids[idx]
        except ValueError:
            pass
    return None

def get_price_history(token_id):
    """Fetches history for the last 24h."""
    end_time = int(time.time())
    start_time = int((datetime.now(timezone.utc) - timedelta(hours=24)).timestamp())
    
    # Try multiple intervals to ensure we get data
    strategies = [
        {"params": {"market": token_id, "startTs": start_time, "endTs": end_time, "interval": "1d"}},
        {"params": {"market": token_id, "startTs": start_time, "endTs": end_time, "interval": "6h"}},
        {"params": {"market": token_id, "interval": "max"}}
    ]

    for strat in strategies:
        try:
            response = requests.get(CLOB_HISTORY_API_URL, params=strat['params'], headers=get_headers())
            if response.status_code == 200:
                history = response.json().get('history', [])
                if history:
                    return history
        except Exception:
            continue
    return []