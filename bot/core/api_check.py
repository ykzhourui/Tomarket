import json
import requests
import re
from bot.utils import logger

baseUrl = "https://api-web.tomarket.ai/tomarket-game/v1"

api_endpoints = [
    r"https://api-web.tomarket.ai/tomarket-game/v1",
    r"/user/login",
    r"/user/balance",
    r"/daily/claim",
    r"/tasks/list",
    r"/tasks/start",
    r"/tasks/check",
    r"/tasks/claim",
    r"/user/tickets",
    r"/spin/raffle",
    r"/tasks/puzzle",
    r"/tasks/puzzleClaim",
    r"/tasks/classmateTask",
    r"/tasks/classmateStars",
]

def get_main_js_format(base_url):
    try:
        response = requests.get(base_url)
        response.raise_for_status()
        content = response.text
        
        matches = re.findall(r'src="(/.*?/index.*?\.js)"', content)
        if matches:
            return sorted(set(matches), key=len, reverse=True)
        else:
            return None
    except requests.RequestException as e:
        logger.error(f"Error fetching the base URL: {e}")
        return None

def get_base_api(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        content = response.text
        
        # Check if each API endpoint pattern matches any part of the JS content
        missing_endpoints = [pattern for pattern in api_endpoints if not re.search(pattern, content)]
        
        if not missing_endpoints:
            return True
        else:
            logger.error("<red>Missing endpoints:</red>", missing_endpoints)
            return False
    except requests.RequestException as e:
        logger.error(f"Error fetching the JS file: {e}")
        return None

def check_base_url():
    base_url = "https://mini-app.tomarket.ai/"
    main_js_formats = get_main_js_format(base_url)

    if main_js_formats:
        for format in main_js_formats:
            full_url = f"https://mini-app.tomarket.ai/{format}"
            result = get_base_api(full_url)

            if result:
                return True
            else:
                return False
    else:
        logger.error("Could not find any main.js format. Dumping page content for inspection:")
        try:
            response = requests.get(base_url)
            logger.error(response.text[:1000])
        except requests.RequestException as e:
            logger.error(f"Error fetching the base URL for content dump: {e}")
        return False

def get_version_info():
    try:
        response = requests.get("https://raw.githubusercontent.com/yanpaing007/Tomarket/refs/heads/main/bot/config/combo.json")
        response.raise_for_status()
        data = response.json()
        version = data.get('version', None)
        message = data.get('message', None)
        return version, message
    except requests.RequestException as e:
        logger.error(f"Error fetching the version info: {e}")
        return None, None
    
def get_local_version_info():
    try:
        with open('bot/config/combo.json', 'r') as local_file:
            data = json.load(local_file)
            version = data.get('version', None)
            return version

    except FileNotFoundError:
            logger.error(f"Local file combo.json not found.")
    except json.JSONDecodeError as json_err:
            logger.error(f"Error parsing JSON from local file: {json_err}")

    return None