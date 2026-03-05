"""
PriceHunt - Backend Scraper
Deploy this on PythonAnywhere (free account)
Scrapes BigBasket & Blinkit for fruit/vegetable prices
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import json
import re
import time
import random

app = Flask(__name__)
CORS(app)  # Allow requests from your Hostinger website

# ===== HEADERS to mimic a real browser =====
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

def scrape_bigbasket(product_name, city="Bangalore", pincode="560043"):
    """Scrape BigBasket for product price"""
    try:
        # BigBasket search URL
        search_url = f"https://www.bigbasket.com/ps/?q={requests.utils.quote(product_name)}&nc=as"

        session = requests.Session()
        session.headers.update(HEADERS)

        # First visit homepage to get cookies
        session.get("https://www.bigbasket.com/", timeout=10)
        time.sleep(random.uniform(1, 2))

        # Set location via BB's API
        location_url = "https://www.bigbasket.com/tb-api/v1/auth/set-location/"
        location_data = {
            "area_id": "",
            "city": city,
            "pincode": pincode
        }
        session.post(location_url, json=location_data, timeout=10)
        time.sleep(random.uniform(0.5, 1))

        # Try their internal search API
        api_url = f"https://www.bigbasket.com/product/get-products/?slug={requests.utils.quote(product_name)}&page=1&tab_type=[%22prd%22]&intent=false&listtype=pc"

        resp = session.get(api_url, timeout=15)

        if resp.status_code == 200:
            try:
                data = resp.json()
                # Navigate BigBasket's response structure
                products_data = None

                if "tab_info" in data:
                    for tab in data.get("tab_info", []):
                        if tab.get("tab_type") == "prd":
                            products_data = tab.get("product_info", {}).get("products", [])
                            break

                if products_data and len(products_data) > 0:
                    # Get first product that matches
                    for prod in products_data[:5]:
                        prod_desc = prod.get("desc", "").lower()
                        search_term = product_name.lower()

                        # Check if product name is in description
                        if any(word in prod_desc for word in search_term.split()):
                            price_info = prod.get("pricing", {})
                            selling_price = price_info.get("discount", {}).get("dsc_prd_price")
                            if not selling_price:
                                selling_price = price_info.get("totalPrice", {}).get("sp")

                            if selling_price:
                                return {
                                    "site": "bigbasket",
                                    "price": float(str(selling_price).replace("₹", "").replace(",", "").strip()),
                                    "product_found": prod.get("desc", product_name)[:40],
                                    "error": None
                                }

                # Fallback: try simpler search
                return scrape_bigbasket_fallback(product_name, session)

            except (json.JSONDecodeError, KeyError):
                return scrape_bigbasket_fallback(product_name, session)

        return scrape_bigbasket_fallback(product_name, session)

    except requests.exceptions.Timeout:
        return {"site": "bigbasket", "price": None, "product_found": None, "error": "Timeout - try again"}
    except Exception as e:
        return {"site": "bigbasket", "price": None, "product_found": None, "error": f"Error: {str(e)[:50]}"}


def scrape_bigbasket_fallback(product_name, session=None):
    """Alternative BigBasket scraping method using their custompage API"""
    try:
        if not session:
            session = requests.Session()
            session.headers.update(HEADERS)

        # Use the known working BigBasket slug API
        slug = product_name.lower().replace(" ", "-")
        url = f"https://www.bigbasket.com/custompage/sysgenpd/?type=pc&slug={slug}"
        resp = session.get(url, timeout=12)

        if resp.status_code == 200:
            try:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    item = data[0]
                    sp = item.get("sp") or item.get("mrp")
                    if sp:
                        return {
                            "site": "bigbasket",
                            "price": float(str(sp).replace(",", "").strip()),
                            "product_found": item.get("p_desc", product_name)[:40],
                            "error": None
                        }
            except:
                pass

        return {"site": "bigbasket", "price": None, "product_found": None, "error": "Not found on BigBasket"}

    except Exception as e:
        return {"site": "bigbasket", "price": None, "product_found": None, "error": "BigBasket unavailable"}


def scrape_blinkit(product_name, city="Bangalore", pincode="560043"):
    """Scrape Blinkit for product price"""
    try:
        session = requests.Session()

        blinkit_headers = {
            **HEADERS,
            "app_client": "consumer",
            "web-version": "1.0.0",
            "Referer": "https://blinkit.com/",
            "Origin": "https://blinkit.com",
        }
        session.headers.update(blinkit_headers)

        # Step 1: Set location on Blinkit using pincode
        location_api = f"https://blinkit.com/v1/address/pincode?pincode={pincode}"
        loc_resp = session.get(location_api, timeout=10)
        time.sleep(random.uniform(0.8, 1.5))

        lat, lng = None, None
        if loc_resp.status_code == 200:
            try:
                loc_data = loc_resp.json()
                coords = loc_data.get("data", {})
                lat = coords.get("lat")
                lng = coords.get("lng")
            except:
                pass

        # Step 2: Search for the product
        search_query = requests.utils.quote(product_name)

        if lat and lng:
            search_url = f"https://blinkit.com/v6/search/products?search={search_query}&start=0&size=10&lat={lat}&lon={lng}"
        else:
            # Fallback coordinates for Bangalore 560043
            search_url = f"https://blinkit.com/v6/search/products?search={search_query}&start=0&size=10&lat=12.9716&lon=77.5946"

        resp = session.get(search_url, timeout=15)

        if resp.status_code == 200:
            try:
                data = resp.json()
                objects = data.get("objects", [])

                for obj in objects[:5]:
                    prod_name = obj.get("name", "").lower()
                    search_term = product_name.lower()

                    if any(word in prod_name for word in search_term.split()):
                        price = obj.get("price") or obj.get("mrp")
                        if price:
                            return {
                                "site": "blinkit",
                                "price": float(str(price).replace("₹", "").replace(",", "").strip()),
                                "product_found": obj.get("name", product_name)[:40],
                                "error": None
                            }

                # No match found
                return {"site": "blinkit", "price": None, "product_found": None, "error": "Not found on Blinkit"}

            except (json.JSONDecodeError, KeyError) as e:
                return {"site": "blinkit", "price": None, "product_found": None, "error": "Could not read Blinkit data"}

        elif resp.status_code == 429:
            return {"site": "blinkit", "price": None, "product_found": None, "error": "Rate limited - wait 1 min"}
        else:
            return {"site": "blinkit", "price": None, "product_found": None, "error": f"Blinkit blocked (HTTP {resp.status_code})"}

    except requests.exceptions.Timeout:
        return {"site": "blinkit", "price": None, "product_found": None, "error": "Timeout - try again"}
    except Exception as e:
        return {"site": "blinkit", "price": None, "product_found": None, "error": f"Error: {str(e)[:50]}"}


# ===== ROUTES =====

@app.route('/')
def home():
    return jsonify({"status": "PriceHunt API running ✅", "version": "1.0"})


@app.route('/scrape', methods=['POST'])
def scrape():
    """Main scrape endpoint called by the frontend"""
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

        # Scrape each requested site
        for site in sites:
            time.sleep(random.uniform(0.3, 0.8))  # Be polite, avoid rate limiting

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
    return jsonify({"status": "ok", "message": "PriceHunt is alive!"})


# ===== RUN =====
if __name__ == '__main__':
    app.run(debug=False)
