import re, json
import base64

def get_tg_auth_result(window_location_hash):
    location_hash = window_location_hash
    re_pattern = r'[#\?\&]tgAuthResult=([A-Za-z0-9\-_=]*)$'
    match = re.search(re_pattern, location_hash)

    try:
        if match:
            location_hash = location_hash.replace(match.group(), '')
            data = match.group(1) or ''
            data = data.replace('-', '+').replace('_', '/')
            pad = len(data) % 4
            if pad > 1:
                data += '=' * (5 - pad)
            decoded_data = base64.b64decode(data)
            return json.loads(decoded_data)
    except Exception as e:
        print(e)
    return False
