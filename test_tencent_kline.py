import requests
import json

def test_tencent_kline(code):
    url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,,,320,qfq"
    print(f"Fetching {url}...")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            print("Response keys:", data.keys())
            if 'data' in data and code in data['data']:
                kline_data = data['data'][code].get('qfqday', [])
                if not kline_data:
                    kline_data = data['data'][code].get('day', []) # 可能是未复权
                
                print(f"Got {len(kline_data)} records.")
                if kline_data:
                    print("First record:", kline_data[0])
            else:
                print("Code not found in data")
        else:
            print(f"Status code: {resp.status_code}")
    except Exception as e:
        print(f"Error: {e}")

test_tencent_kline("sh600519")
test_tencent_kline("sz000001")

