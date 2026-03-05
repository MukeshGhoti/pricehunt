"""
PriceHunt - Backend Scraper v3
Uses BigBasket + JioMart + DMart
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import json
import re
import time
import random

app = Flask(__name__)
CORS(app)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
]

def base_headers(referer=""):
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json, text/html, */*",
        "Accept-Language": "en-IN,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": referer,
        "Connection": "keep-alive",
    }

def scrape_bigbasket(product_name, city="Bangalore", pincode="560043"):
    try:
        session = requests.Session()
        session.headers.update(base_headers("https://www.bigbasket.com/"))
        session.get("https://www.bigbasket.com/", timeout=12)
        time.sleep(random.uniform(1.5, 2.5))
        csrf = session.cookies.get("csrftoken", "")
        if csrf:
            session.headers.update({"X-CSRFToken": csrf, "x-channel": "BB-WEB"})
        try:
            session.post("https://www.bigbasket.com/tb-api/v1/auth/set-location/",
                json={"area_id": "", "city": city, "pincode": pincode}, timeout=8)
            time.sleep(1)
        except:
            pass
        encoded = requests.utils.quote(product_name)
        api_url = f"https://www.bigbasket.com/product/get-products/?slug={encoded}&page=1&tab_type=%5B%22prd%22%5D&intent=false&listtype=pc"
        resp = session.get(api_url, timeout=15)
        if resp.status_code == 200:
            try:
                data = resp.json()
                for tab in data.get("tab_info", []):
                    if tab.get("tab_type") == "prd":
                        products = tab.get("product_info", {}).get("products", [])
                        for prod in products[:8]:
                            desc = prod.get("desc", "").lower()
                            if any(w in desc for w in product_name.lower().split()):
                                pricing = prod.get("pricing", {})
                                sp = (pricing.get("discount", {}).get("dsc_prd_price")
                                      or pricing.get("totalPrice", {}).get("sp"))
                                if sp:
                                    return {"site": "bigbasket",
                                        "price": float(str(sp).replace("₹","").replace(",","").strip()),
                                        "product_found": prod.get("desc", product_name)[:50],
                                        "error": None}
            except:
                pass
        session.headers.update({"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"})
        html_resp = session.get(f"https://www.bigbasket.com/ps/?q={encoded}&nc=as", timeout=15)
        if html_resp.status_code == 200:
            for pattern in [r'"sp"\s*:\s*(\d+\.?\d*)', r'"price"\s*:\s*(\d+\.?\d*)']:
                matches = re.findall(pattern, html_resp.text)
                prices = [float(m) for m in matches if 5 <= float(m) <= 2000]
                if prices:
                    return {"site": "bigbasket", "price": min(prices),
                        "product_found": f"{product_name} (BigBasket)", "error": None}
        return {"site": "bigbasket", "price": None, "product_found": None, "error": "Not found on BigBasket"}
    except requests.exceptions.Timeout:
        return {"site": "bigbasket", "price": None, "product_found": None, "error": "Timeout - try again"}
    except Exception as e:
        return {"site": "bigbasket", "price": None, "product_found": None, "error": f"BigBasket error: {str(e)[:40]}"}

def scrape_jiomart(product_name, city="Bangalore", pincode="560043"):
    try:
        session = requests.Session()
        session.headers.update(base_headers("https://www.jiomart.com/"))
        session.get("https://www.jiomart.com/", timeout=12)
        time.sleep(random.uniform(1.0, 2.0))
        encoded = requests.utils.quote(product_name)
        session.headers.update({"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"})
        resp = session.get(f"https://www.jiomart.com/search/{encoded}", timeout=15)
        if resp.status_code == 200:
            html = resp.text
            json_match = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?});', html, re.DOTALL)
            if json_match:
                try:
                    data = json.loads(json_match.group(1))
                    products = (data.get("search", {}).get("products")
                                or data.get("products", {}).get("items", []))
                    for prod in (products or [])[:5]:
                        name = (prod.get("name") or prod.get("title") or "").lower()
                        if any(w in name for w in product_name.lower().split()):
                            price = prod.get("price") or prod.get("special_price") or prod.get("final_price")
                            if price:
                                return {"site": "jiomart",
                                    "price": float(str(price).replace("₹","").replace(",","").strip()),
                                    "product_found": (prod.get("name") or product_name)[:50],
                                    "error": None}
                except:
                    pass
            for pattern in [r'"price"\s*:\s*"?(\d+\.?\d*)"?', r'"special_price"\s*:\s*"?(\d+\.?\d*)"?', r'₹\s*(\d+)']:
                matches = re.findall(pattern, html)
                prices = [float(m) for m in matches if 5 <= float(m) <= 2000]
                if prices:
                    return {"site": "jiomart", "price": min(prices),
                        "product_found": f"{product_name} (JioMart)", "error": None}
        return {"site": "jiomart", "price": None, "product_found": None, "error": "Not found on JioMart"}
    except requests.exceptions.Timeout:
        return {"site": "jiomart", "price": None, "product_found": None, "error": "Timeout - try again"}
    except Exception as e:
        return {"site": "jiomart", "price": None, "product_found": None, "error": f"JioMart error: {str(e)[:40]}"}

def scrape_dmart(product_name, city="Bangalore", pincode="560043"):
    try:
        session = requests.Session()
        session.headers.update({**base_headers("https://www.dmart.in/"), "Accept": "application/json, text/plain, */*"})
        session.get("https://www.dmart.in/", timeout=12)
        time.sleep(random.uniform(1.0, 2.0))
        encoded = requests.utils.quote(product_name)
        search_url = f"https://www.dmart.in/api/product/get-product-by-search?searchParam={encoded}&pageNo=0&pageSize=10&channel=WEB&pincode={pincode}"
        resp = session.get(search_url, timeout=15)
        if resp.status_code == 200:
            try:
                data = resp.json()
                items = (data.get("data", {}).get("product_list") or data.get("products") or data.get("data", []))
                if isinstance(items, dict):
                    items = items.get("items", [])
                for item in (items or [])[:5]:
                    name = (item.get("product_name") or item.get("name") or "").lower()
                    if any(w in name for w in product_name.lower().split()):
                        price = (item.get("offer_price") or item.get("selling_price") or item.get("mrp"))
                        if price:
                            return {"site": "dmart",
                                "price": float(str(price).replace("₹","").replace(",","").strip()),
                                "product_found": (item.get("product_name") or product_name)[:50],
                                "error": None}
            except:
                pass
        return {"site": "dmart", "price": None, "product_found": None, "error": "Not found on DMart"}
    except requests.exceptions.Timeout:
        return {"site": "dmart", "price": None, "product_found": None, "error": "Timeout - try again"}
    except Exception as e:
        return {"site": "dmart", "price": None, "product_found": None, "error": f"DMart error: {str(e)[:40]}"}

@app.route('/')
def home():
    return jsonify({"status": "PriceHunt API running", "version": "3.0"})

@app.route('/scrape', methods=['POST'])
def scrape():
    try:
        body = request.get_json()
        if not body:
            return jsonify({"error": "No data sent"}), 400
        product = body.get("product", "").strip()
        city = body.get("city", "Bangalore")
        pincode = body.get("pincode", "560043")
        sites = body.get("sites", ["bigbasket", "jiomart"])
        if not product:
            return jsonify({"error": "Product name is required"}), 400
        scraper_map = {"bigbasket": scrape_bigbasket, "blinkit": scrape_bigbasket,
                       "jiomart": scrape_jiomart, "dmart": scrape_dmart}
        results = []
        seen = set()
        for site in sites:
            time.sleep(random.uniform(0.5, 1.0))
            fn = scraper_map.get(site)
            key = "bigbasket" if site == "blinkit" else site
            if key in seen or not fn:
                continue
            seen.add(key)
            result = fn(product, city, pincode)
            result["site"] = key
            results.append(result)
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "message": "PriceHunt v3 alive!"})

if __name__ == '__main__':
    app.run(debug=False)
