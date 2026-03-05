"""
PriceHunt - Backend Scraper v2
Improved scraping for BigBasket & Blinkit
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

# Rotate user agents to avoid detection
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
]

def get_headers(referer=""):
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json, text/html, */*",
        "Accept-Language": "en-IN,en-GB;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Referer": referer,
        "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }


def scrape_bigbasket(product_name, city="Bangalore", pincode="560043"):
    """Scrape BigBasket using their search page"""
    try:
        session = requests.Session()
        session.headers.update(get_headers("https://www.bigbasket.com/"))

        # Step 1: Visit homepage to get cookies + csrftoken
        home_resp = session.get("https://www.bigbasket.com/", timeout=12)
        time.sleep(random.uniform(1.0, 2.0))

        # Get CSRF token from cookies
        csrf = session.cookies.get("csrftoken", "")

        if csrf:
            session.headers.update({
                "X-CSRFToken": csrf,
                "x-channel": "BB-WEB",
            })

        # Step 2: Set city/pincode
        try:
            session.post(
                "https://www.bigbasket.com/tb-api/v1/auth/set-location/",
                json={"area_id": "", "city": city, "pincode": pincode},
                timeout=8
            )
            time.sleep(random.uniform(0.5, 1.0))
        except:
            pass

        # Step 3: Try the search API
        encoded = requests.utils.quote(product_name)
        api_url = f"https://www.bigbasket.com/product/get-products/?slug={encoded}&page=1&tab_type=%5B%22prd%22%5D&intent=false&listtype=pc"

        resp = session.get(api_url, timeout=15)

        if resp.status_code == 200:
            try:
                data = resp.json()
                for tab in data.get("tab_info", []):
                    if tab.get("tab_type") == "prd":
                        products = tab.get("product_info", {}).get("products", [])
                        for prod in products[:5]:
                            desc = prod.get("desc", "").lower()
                            if any(w in desc for w in product_name.lower().split()):
                                pricing = prod.get("pricing", {})
                                sp = (pricing.get("discount", {}).get("dsc_prd_price")
                                      or pricing.get("totalPrice", {}).get("sp"))
                                if sp:
                                    return {
                                        "site": "bigbasket",
                                        "price": float(str(sp).replace("₹", "").replace(",", "").strip()),
                                        "product_found": prod.get("desc", product_name)[:50],
                                        "error": None
                                    }
            except:
                pass

        # Step 4: Fallback — scrape search results page HTML
        search_url = f"https://www.bigbasket.com/ps/?q={encoded}&nc=as"
        session.headers.update({"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"})
        html_resp = session.get(search_url, timeout=15)

        if html_resp.status_code == 200:
            html = html_resp.text
            # Look for price patterns in the HTML
            price_patterns = [
                r'"sp"\s*:\s*(\d+\.?\d*)',
                r'"price"\s*:\s*(\d+\.?\d*)',
                r'₹\s*(\d+\.?\d*)',
                r'"mrp"\s*:\s*(\d+\.?\d*)',
            ]
            for pattern in price_patterns:
                matches = re.findall(pattern, html)
                if matches:
                    # Filter reasonable grocery prices (₹5 - ₹2000)
                    prices = [float(m) for m in matches if 5 <= float(m) <= 2000]
                    if prices:
                        return {
                            "site": "bigbasket",
                            "price": min(prices),
                            "product_found": f"{product_name} (BigBasket)",
                            "error": None
                        }

        return {"site": "bigbasket", "price": None, "product_found": None, "error": "Not found on BigBasket"}

    except requests.exceptions.Timeout:
        return {"site": "bigbasket", "price": None, "product_found": None, "error": "Timeout - try again"}
    except Exception as e:
        return {"site": "bigbasket", "price": None, "product_found": None, "error": f"BigBasket error: {str(e)[:40]}"}


def scrape_blinkit(product_name, city="Bangalore", pincode="560043"):
    """Scrape Blinkit with improved headers"""
    try:
        session = requests.Session()

        # Blinkit needs specific headers
        session.headers.update({
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-IN,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "app_client": "consumer",
            "web-version": "2.0",
            "Referer": "https://blinkit.com/",
            "Origin": "https://blinkit.com",
            "Connection": "keep-alive",
        })

        # Step 1: Visit homepage first to get cookies
        try:
            session.get("https://blinkit.com/", timeout=10)
            time.sleep(random.uniform(1.0, 2.0))
        except:
            pass

        # Step 2: Get coordinates for pincode
        lat, lng = 12.9716, 77.5946  # Default Bangalore 560043

        try:
            loc_resp = session.get(
                f"https://blinkit.com/v1/address/pincode?pincode={pincode}",
                timeout=10
            )
            if loc_resp.status_code == 200:
                loc_data = loc_resp.json()
                coords = loc_data.get("data", {})
                lat = coords.get("lat", lat)
                lng = coords.get("lng", lng)
            time.sleep(random.uniform(0.5, 1.0))
        except:
            pass

        # Step 3: Search for product
        encoded = requests.utils.quote(product_name)
        search_url = f"https://blinkit.com/v6/search/products?search={encoded}&start=0&size=10&lat={lat}&lon={lng}"

        resp = session.get(search_url, timeout=15)

        if resp.status_code == 200:
            try:
                data = resp.json()
                objects = data.get("objects", [])
                for obj in objects[:5]:
                    name = obj.get("name", "").lower()
                    if any(w in name for w in product_name.lower().split()):
                        price = obj.get("price") or obj.get("mrp")
                        if price:
                            return {
                                "site": "blinkit",
                                "price": float(str(price).replace("₹", "").replace(",", "").strip()),
                                "product_found": obj.get("name", product_name)[:50],
                                "error": None
                            }
                return {"site": "blinkit", "price": None, "product_found": None, "error": "Not found on Blinkit"}
            except:
                pass

        elif resp.status_code == 403:
            # Try alternate Blinkit API endpoint
            return scrape_blinkit_alternate(product_name, lat, lng, session)

        elif resp.status_code == 429:
            return {"site": "blinkit", "price": None, "product_found": None, "error": "Rate limited - wait 1 min"}

        return {"site": "blinkit", "price": None, "product_found": None, "error": f"Blinkit blocked (HTTP {resp.status_code})"}

    except requests.exceptions.Timeout:
        return {"site": "blinkit", "price": None, "product_found": None, "error": "Timeout - try again"}
    except Exception as e:
        return {"site": "blinkit", "price": None, "product_found": None, "error": f"Blinkit error: {str(e)[:40]}"}


def scrape_blinkit_alternate(product_name, lat, lng, session):
    """Try alternate Blinkit endpoints"""
    try:
        encoded = requests.utils.quote(product_name)

        # Try v2 search endpoint
        urls_to_try = [
            f"https://blinkit.com/v2/search/products?search={encoded}&lat={lat}&lon={lng}",
            f"https://blinkit.com/search?q={encoded}",
        ]

        for url in urls_to_try:
            try:
                resp = session.get(url, timeout=12)
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        # Try different response structures
                        for key in ["objects", "products", "data", "results"]:
                            items = data.get(key, [])
                            if items:
                                for item in items[:5]:
                                    name = (item.get("name") or item.get("title") or "").lower()
                                    if any(w in name for w in product_name.lower().split()):
                                        price = item.get("price") or item.get("mrp") or item.get("sp")
                                        if price:
                                            return {
                                                "site": "blinkit",
                                                "price": float(str(price).replace("₹", "").replace(",", "").strip()),
                                                "product_found": item.get("name", product_name)[:50],
                                                "error": None
                                            }
                    except:
                        pass
                time.sleep(0.5)
            except:
                pass

        return {"site": "blinkit", "price": None, "product_found": None, "error": "Blinkit unavailable - try later"}

    except Exception:
        return {"site": "blinkit", "price": None, "product_found": None, "error": "Blinkit unavailable"}


# ===== ROUTES =====

@app.route('/')
def home():
    return jsonify({"status": "PriceHunt API running ✅", "version": "2.0"})


@app.route('/scrape', methods=['POST'])
def scrape():
    try:
        body = request.get_json()
        if not body:
            return jsonify({"error": "No data sent"}), 400

        product = body.get("product", "").strip()
        city = body.get("city", "Bangalore")
        pincode = body.get("pincode", "560043")
        sites = body.get("sites", ["bigbasket", "blinkit"])

        if not product:
            return jsonify({"error": "Product name is required"}), 400

        results = []
        for site in sites:
            time.sleep(random.uniform(0.5, 1.0))
            if site == "bigbasket":
                result = scrape_bigbasket(product, city, pincode)
            elif site == "blinkit":
                result = scrape_blinkit(product, city, pincode)
            else:
                result = {"site": site, "price": None, "product_found": None, "error": "Site not supported"}
            results.append(result)

        return jsonify(results)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "message": "PriceHunt v2 is alive!"})


if __name__ == '__main__':
    app.run(debug=False)
