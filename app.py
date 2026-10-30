import asyncio
import json
import re
from urllib.parse import quote_plus
import httpx
from bs4 import BeautifulSoup
import pandas as pd
import streamlit as st
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# ----------------- STREAMLIT PAGE CONFIG -----------------
st.set_page_config(
    page_title="Indian Drone Parts Sourcing Agent",
    page_icon="🛸",
    layout="wide"
)

# ----------------- STRUCTURED OUTPUT SCHEMA -----------------
class DronePartItem(BaseModel):
    product_name: str = Field(description="Full clean title of the product")
    specification: str = Field(description="Key technical specs extracted (e.g., KV, Voltage, Current, Size, Frequency)")
    brand_name: str = Field(description="Manufacturer or brand name (e.g., SpeedyBee, T-Motor, Hobbywing, Radiomaster, Generic)")
    vendor_name: str = Field(description="Store name where product is listed")
    sku_name: str = Field(description="SKU or product code if available, else 'N/A'")
    rate: float = Field(description="Numeric price in INR (Rs/₹). Must be greater than 0.")
    in_stock: bool = Field(description="True ONLY if the item is currently available to buy/in stock")
    link: str = Field(description="Direct URL to the product page")

class SourcingResponse(BaseModel):
    matched_parts: list[DronePartItem]

class SearchKeywords(BaseModel):
    keywords: list[str] = Field(description="3 to 4 short search keyword variations for vendor search bars")

# ----------------- VENDOR REGISTRY -----------------
WOOCOMMERCE_VENDORS = {
    "Robu": "https://robu.in",
    "Zbotic": "https://zbotic.in",
    "Tujo RC": "https://tujorc.com",
    "Quadkart": "https://www.quadkart.in",
    "Design Info": "https://www.designinfo.in",
    "Anubis Tech": "https://anubisrc.com",
    "FPV Guru": "https://fpvguru.in",
}

SHOPIFY_VENDORS = {
    "Hi Tech XYZ": "https://hitechxyz.in",
    "Xrobo": "https://xrobo.in",
}

CUSTOM_VENDORS = {
    "Robokits": "https://robokits.co.in/index.php?main_page=advanced_search_result&keyword=",
    "Indian Robo Store": "https://indianrobostore.com/search?q=",
    "UAV Marketplace": "https://www.uavmarketplace.in/search?q=",
}

DANNY_NOTION_URL = "https://danny8.notion.site/Danny-s-Inventory-List-214fd82319444160b57ffdf5ebb118bd"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# ----------------- STEP 1: QUERY EXPANSION -----------------
def expand_search_queries(client: genai.Client, item_name: str, specs: str) -> list[str]:
    prompt = f"""
    You are an FPV and UAV hardware sourcing specialist in India.
    User is looking for:
    Item Name: {item_name}
    Required Specifications: {specs}

    Generate 3 short, high-recall search queries that Indian drone e-commerce search bars (WooCommerce/Shopify) will match.
    Include common naming variations or abbreviations (e.g., 'ELRS' vs 'ExpressLRS', 'FC' vs 'Flight Controller', '50A' vs '50 Amp').
    Keep each query between 2 and 4 words maximum so vendor search bars don't fail.
    """
    try:
        res = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SearchKeywords,
                temperature=0.1,
            ),
        )
        data = json.loads(res.text)
        queries = data.get("keywords", [item_name])
        if item_name not in queries:
            queries.insert(0, item_name)
        return queries[:3]
    except Exception:
        return [item_name]

# ----------------- STEP 2: ASYNC VENDOR SCRAPERS -----------------
async def fetch_woocommerce(session: httpx.AsyncClient, vendor: str, base_url: str, query: str) -> list[dict]:
    """Tries WooCommerce Store API first, falls back to HTML search parsing."""
    results = []
    api_url = f"{base_url}/wp-json/wc/store/v1/products?search={quote_plus(query)}&per_page=12"
    try:
        resp = await session.get(api_url, timeout=12.0)
        if resp.status_code == 200 and "application/json" in resp.headers.get("content-type", ""):
            items = resp.json()
            for item in items:
                if not item.get("is_in_stock", True):
                    continue
                prices = item.get("prices", {})
                raw_price = prices.get("price", "0")
                minor_unit = prices.get("currency_minor_unit", 2)
                price_val = float(raw_price) / (10 ** minor_unit) if raw_price else 0
                results.append({
                    "vendor": vendor,
                    "title": item.get("name", ""),
                    "sku": item.get("sku", "N/A"),
                    "price": price_val,
                    "in_stock": item.get("is_in_stock", True),
                    "link": item.get("permalink", ""),
                    "raw_desc": BeautifulSoup(item.get("short_description", ""), "html.parser").get_text(" ", strip=True)[:250]
                })
            if results:
                return results
    except Exception:
        pass

    # Fallback: Standard WooCommerce HTML Search
    search_url = f"{base_url}/?s={quote_plus(query)}&post_type=product"
    try:
        resp = await session.get(search_url, timeout=12.0)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for prod in soup.select(".product, li.product, .product-grid-item")[:10]:
                text_blob = prod.get_text(" ", strip=True)
                if re.search(r"out of stock|sold out|read more", text_blob, re.I):
                    continue
                a_tag = prod.select_one("a.woocommerce-LoopProduct-link, h2 a, h3 a, .product-title a, a")
                link = a_tag["href"] if a_tag and a_tag.has_attr("href") else search_url
                results.append({
                    "vendor": vendor,
                    "raw_snippet": text_blob[:350],
                    "link": link
                })
    except Exception:
        pass
    return results

async def fetch_shopify(session: httpx.AsyncClient, vendor: str, base_url: str, query: str) -> list[dict]:
    """Uses Shopify Predictive Search JSON API."""
    results = []
    api_url = f"{base_url}/search/suggest.json?q={quote_plus(query)}&resources[type]=product&resources[limit]=10"
    try:
        resp = await session.get(api_url, timeout=12.0)
        if resp.status_code == 200:
            data = resp.json()
            products = data.get("resources", {}).get("results", {}).get("products", [])
            for p in products:
                if not p.get("available", True):
                    continue
                results.append({
                    "vendor": vendor,
                    "title": p.get("title", ""),
                    "brand": p.get("vendor", ""),
                    "sku": p.get("variants", [{}])[0].get("sku", "N/A") if p.get("variants") else "N/A",
                    "price": float(p.get("price", 0)),
                    "in_stock": p.get("available", True),
                    "link": f"{base_url}{p.get('url', '')}",
                    "raw_desc": BeautifulSoup(p.get("body", ""), "html.parser").get_text(" ", strip=True)[:250]
                })
    except Exception:
        pass
    return results

async def fetch_custom_and_notion(session: httpx.AsyncClient, vendor: str, target_url: str) -> list[dict]:
    """Uses Jina Reader proxy to cleanly parse JS-rendered stores (UAV Marketplace, Indian Robo Store, Notion)."""
    results = []
    jina_url = f"https://r.jina.ai/{target_url}"
    try:
        resp = await session.get(jina_url, timeout=15.0)
        if resp.status_code == 200 and len(resp.text) > 100:
            results.append({
                "vendor": vendor,
                "raw_markdown": resp.text[:4500],
                "link": target_url
            })
    except Exception:
        pass
    return results

async def gather_all_vendors(queries: list[str], selected_vendors: list[str]) -> list[dict]:
    all_raw = []
    primary_query = queries[0]
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as session:
        tasks = []
        # Queue WooCommerce tasks across expanded queries
        for vendor, url in WOOCOMMERCE_VENDORS.items():
            if vendor in selected_vendors:
                for q in queries[:2]:
                    tasks.append(fetch_woocommerce(session, vendor, url, q))

        # Queue Shopify tasks
        for vendor, url in SHOPIFY_VENDORS.items():
            if vendor in selected_vendors:
                for q in queries[:2]:
                    tasks.append(fetch_shopify(session, vendor, url, q))

        # Queue Custom stores
        for vendor, search_prefix in CUSTOM_VENDORS.items():
            if vendor in selected_vendors:
                tasks.append(fetch_custom_and_notion(session, vendor, f"{search_prefix}{quote_plus(primary_query)}"))

        # Queue Danny's Notion Inventory
        if "Danny’s Inventory List" in selected_vendors:
            tasks.append(fetch_custom_and_notion(session, "Danny’s Inventory List", DANNY_NOTION_URL))

        responses = await asyncio.gather(*tasks, return_exceptions=True)
        for r in responses:
            if isinstance(r, list):
                all_raw.extend(r)
    return all_raw

# ----------------- STEP 3: GEMINI SEMANTIC FILTER & EXTRACTION -----------------
def filter_and_structure_results(client: genai.Client, item_name: str, specs: str, raw_candidates: list[dict]) -> list[dict]:
    if not raw_candidates:
        return []

    prompt = f"""
    You are an expert drone hardware procurement agent.
    The user is searching for:
    - Target Item: {item_name}
    - Required Specification: {specs}

    Below is raw scraped product data from Indian drone vendors.
    Rules:
    1. Filter for products that genuinely match the target item and specification (even if named slightly differently, e.g., synonym or model shorthand).
    2. Exclude irrelevant accessories (e.g., if user wants a 'Frame', exclude replacement arms or screws unless requested; if user wants a 'Motor', exclude spare bells).
    3. Strictly exclude any item marked 'Out of Stock', 'Sold Out', or 'in_stock: false'.
    4. Extract Product Name, concise Specification, Brand Name, Vendor Name, SKU (or 'N/A'), numeric Rate in INR, and direct Link.
    5. Deduplicate identical product links.

    Raw Scraped Data:
    {json.dumps(raw_candidates)[:28000]}
    """
    try:
        res = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SourcingResponse,
                temperature=0.0,
            ),
        )
        parsed = json.loads(res.text)
        return parsed.get("matched_parts", [])
    except Exception as e:
        st.error(f"Error parsing results with Gemini: {e}")
        return []

# ----------------- STREAMLIT UI LAYOUT -----------------
st.title("🛸 Indian Drone Vendor Part Finder Agent")
st.caption("Live parallel search across 13 Indian FPV & UAV vendors — Powered by Gemini 2.5 Flash")

with st.sidebar:
    st.header("⚙️ Agent Configuration")
    api_key = st.text_input(
        "Gemini API Key",
        value=st.secrets.get("GEMINI_API_KEY", "") if "GEMINI_API_KEY" in st.secrets else "",
        type="password",
        help="Get your free API key from aistudio.google.com"
    )
    all_vendor_names = (
        list(WOOCOMMERCE_VENDORS.keys())
        + list(SHOPIFY_VENDORS.keys())
        + list(CUSTOM_VENDORS.keys())
        + ["Danny’s Inventory List"]
    )
    selected_vendors = st.multiselect(
        "Active Vendors (13)",
        options=all_vendor_names,
        default=all_vendor_names
    )

col1, col2 = st.columns([1, 1])
with col1:
    item_input = st.text_input("📦 Item Name / Model", placeholder="e.g., SpeedyBee F405 V4 Stack, 2207 Brushless Motor, ELRS Receiver")
with col2:
    spec_input = st.text_input("🔧 Required Specifications", placeholder="e.g., 55A 4-in-1 ESC, 1950KV 6S, 2.4GHz Nano")

if st.button("🔍 Search Across All Vendors", type="primary", use_container_width=True):
    if not api_key:
        st.warning("Please enter your free Gemini API Key in the sidebar (from aistudio.google.com).")
    elif not item_input:
        st.warning("Please enter an Item Name to search.")
    else:
        client = genai.Client(api_key=api_key)

        with st.status("Running intelligent multi-vendor procurement agent...", expanded=True) as status:
            st.write("🧠 Expanding search terms for naming variations...")
            search_queries = expand_search_queries(client, item_input, spec_input)
            st.write(f"**Generated Search Variations:** `{', '.join(search_queries)}`")

            st.write(f"🌐 Querying {len(selected_vendors)} Indian drone stores in parallel...")
            raw_data = asyncio.run(gather_all_vendors(search_queries, selected_vendors))
            st.write(f"📥 Collected `{len(raw_data)}` raw product listings. Verifying specs & stock with Gemini...")

            matched_items = filter_and_structure_results(client, item_input, spec_input, raw_data)
            status.update(label=f"Search complete! Found {len(matched_items)} matching in-stock items.", state="complete")

        if matched_items:
            df = pd.DataFrame(matched_items)
            df = df[df["in_stock"] == True]
            df = df.sort_values(by="rate", ascending=True).reset_index(drop=True)

            # Rename and order columns to exact requirement
            df_display = df[[
                "product_name", "specification", "brand_name",
                "vendor_name", "sku_name", "rate", "link"
            ]].rename(columns={
                "product_name": "Product Name",
                "specification": "Specification",
                "brand_name": "Brand Name",
                "vendor_name": "Vendor Name",
                "sku_name": "SKU Name",
                "rate": "Rate (₹)",
                "link": "Product Link"
            })

            st.subheader("📊 Available Products (Sorted: Low to High Cost)")
            st.dataframe(
                df_display,
                column_config={
                    "Rate (₹)": st.column_config.NumberColumn("Rate (₹)", format="₹%.2f"),
                    "Product Link": st.column_config.LinkColumn("Link", display_text="View on Store ↗")
                },
                use_container_width=True,
                hide_index=True
            )

            csv_data = df_display.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Download Comparison Table (CSV)",
                data=csv_data,
                file_name=f"drone_parts_{item_input.replace(' ', '_')}.csv",
                mime="text/csv"
            )
        else:
            st.info("No in-stock products matched your exact specifications across the selected vendors. Try broadening your specification keywords.")
