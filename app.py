import asyncio
import json
import re
import time
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
    specification: str = Field(description="Key technical specs extracted or inferred (e.g., KV, Voltage, Current, Size, ELRS)")
    brand_name: str = Field(description="Manufacturer or brand name (e.g., RadioMaster, SpeedyBee, T-Motor, Generic)")
    vendor_name: str = Field(description="Store name where product is listed")
    sku_name: str = Field(description="SKU or product code if available, else 'N/A'")
    rate: float = Field(description="Numeric price in INR (Rs/₹). Use 0 if price is not shown on snippet.")
    in_stock: bool = Field(description="True unless explicitly marked Out of Stock or Sold Out")
    link: str = Field(description="Direct URL to the product page")

class SourcingResponse(BaseModel):
    matched_parts: list[DronePartItem]

class SearchKeywords(BaseModel):
    keywords: list[str] = Field(description="2 short search keyword variations")

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

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}

# ----------------- ROBUST GEMINI CALL WITH BACKOFF RETRY -----------------
def call_gemini_with_retry(client: genai.Client, model_name: str, contents: str, config: types.GenerateContentConfig, max_retries: int = 2):
    models_to_try = [model_name, "gemini-2.0-flash", "gemini-1.5-flash"]
    models_to_try = list(dict.fromkeys(models_to_try))

    for m in models_to_try:
        delay = 3.0
        for attempt in range(max_retries):
            try:
                return client.models.generate_content(
                    model=m,
                    contents=contents,
                    config=config,
                )
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "503" in err_str or "UNAVAILABLE" in err_str:
                    if attempt < max_retries - 1:
                        time.sleep(delay)
                        delay *= 2
                        continue
                if "404" in err_str or "NOT_FOUND" in err_str:
                    break
                if attempt == max_retries - 1 and m == models_to_try[-1]:
                    raise e
    raise Exception("Rate limit reached.")

# ----------------- THOROUGH LOCAL REGEX PARSER -----------------
def fallback_regex_parser(raw_candidates: list[dict], item_query: str) -> list[dict]:
    extracted = []
    query_terms = [t.lower() for t in item_query.split() if len(t) > 2]

    for cand in raw_candidates:
        vendor = cand.get("vendor", "Unknown Vendor")
        link = cand.get("link", "")
        
        # WooCommerce direct JSON items or Robu API items
        if "title" in cand:
            title = cand["title"]
            if not query_terms or any(term in title.lower() for term in query_terms):
                extracted.append({
                    "product_name": title,
                    "specification": cand.get("raw_desc", item_query),
                    "brand_name": "Generic",
                    "vendor_name": vendor,
                    "sku_name": cand.get("sku", "N/A"),
                    "rate": float(cand.get("price", 0)),
                    "in_stock": True,
                    "link": link
                })
            continue

        # Jina markdown payload parsing
        md_text = cand.get("raw_markdown", "")
        lines = md_text.splitlines()
        
        for i, line in enumerate(lines):
            link_match = re.search(r"\[([^\]]+)\]\((https?://[^\)]+)\)", line)
            if link_match:
                t_text = link_match.group(1).strip()
                l_url = link_match.group(2).strip()
                
                if len(t_text) > 8 and not any(w in t_text.lower() for w in ["home", "cart", "account", "login", "search", "wishlist", "compare", "blog", "track"]):
                    if not query_terms or any(term in t_text.lower() for term in query_terms):
                        item_price = 0.0
                        for offset in range(4):
                            if i + offset < len(lines):
                                price_match = re.search(r"(?:₹|Rs\.?)\s*([0-9,]+\.?[0-9]*)", lines[i + offset])
                                if price_match:
                                    try:
                                        p_str = price_match.group(1).replace(",", "")
                                        item_price = float(p_str)
                                        break
                                    except ValueError:
                                        pass
                        
                        extracted.append({
                            "product_name": t_text,
                            "specification": item_query,
                            "brand_name": "Generic",
                            "vendor_name": vendor,
                            "sku_name": "N/A",
                            "rate": item_price,
                            "in_stock": True,
                            "link": l_url if "http" in l_url else link
                        })

    seen_links = set()
    unique_items = []
    for item in extracted:
        if item["link"] not in seen_links:
            seen_links.add(item["link"])
            unique_items.append(item)
    return unique_items

def clean_markdown_noise(md_text: str) -> str:
    cleaned = re.sub(r"!\[.*?\]\(.*?\)", "", md_text)
    lines = [line.strip() for line in cleaned.splitlines() if len(line.strip()) > 2]
    filtered_lines = [
        l for l in lines
        if not any(skip in l.lower() for skip in ["facebook.com", "instagram.com", "linkedin.com", "youtube.com", "twitter.com", "customer support", "privacy policy"])
    ]
    return "\n".join(filtered_lines)[:6000]

# ----------------- STEP 1: QUERY EXPANSION -----------------
def expand_search_queries(client: genai.Client, model_name: str, item_name: str) -> list[str]:
    try:
        prompt = f"Generate 2 short search keyword variations (2-4 words max) for Indian drone stores searching for: {item_name}"
        res = call_gemini_with_retry(
            client,
            model_name,
            prompt,
            types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SearchKeywords,
                temperature=0.1,
            ),
        )
        data = json.loads(res.text)
        queries = data.get("keywords", [item_name])
        if item_name not in queries:
            queries.insert(0, item_name)
        return queries[:2]
    except Exception:
        return [item_name]

# ----------------- STEP 2: SPECIALIZED VENDOR SCRAPERS -----------------
async def fetch_robu_and_zbotic(session: httpx.AsyncClient, vendor: str, base_url: str, query: str) -> list[dict]:
    """Specialized handler for Robu and Zbotic using WooCommerce Store API + Jina Bypass."""
    results = []
    # 1. Try WooCommerce Store API with custom browser headers
    api_url = f"{base_url}/wp-json/wc/store/v1/products?search={quote_plus(query)}&per_page=20"
    try:
        resp = await session.get(api_url, headers=BROWSER_HEADERS, timeout=8.0)
        if resp.status_code == 200 and "application/json" in resp.headers.get("content-type", ""):
            items = resp.json()
            if isinstance(items, list):
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
                        "raw_desc": BeautifulSoup(item.get("short_description", ""), "html.parser").get_text(" ", strip=True)[:150]
                    })
                if results:
                    return results
    except Exception:
        pass

    # 2. Fallback to Jina Reader Proxy for Robu/Zbotic HTML search
    search_url = f"{base_url}/?s={quote_plus(query)}&post_type=product"
    try:
        jina_url = f"https://r.jina.ai/{search_url}"
        resp = await session.get(jina_url, headers=BROWSER_HEADERS, timeout=12.0)
        if resp.status_code == 200 and len(resp.text) > 100:
            results.append({
                "vendor": vendor,
                "raw_markdown": clean_markdown_noise(resp.text),
                "link": search_url
            })
    except Exception:
        pass
    return results

async def fetch_woocommerce(session: httpx.AsyncClient, vendor: str, base_url: str, query: str) -> list[dict]:
    if vendor in ["Robu", "Zbotic"]:
        return await fetch_robu_and_zbotic(session, vendor, base_url, query)

    results = []
    api_url = f"{base_url}/wp-json/wc/store/v1/products?search={quote_plus(query)}&per_page=20"
    try:
        resp = await session.get(api_url, headers=BROWSER_HEADERS, timeout=8.0)
        if resp.status_code == 200 and "application/json" in resp.headers.get("content-type", ""):
            items = resp.json()
            if isinstance(items, list):
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
                        "raw_desc": BeautifulSoup(item.get("short_description", ""), "html.parser").get_text(" ", strip=True)[:150]
                    })
    except Exception:
        pass

    search_url = f"{base_url}/?s={quote_plus(query)}&post_type=product"
    try:
        jina_url = f"https://r.jina.ai/{search_url}"
        resp = await session.get(jina_url, headers=BROWSER_HEADERS, timeout=12.0)
        if resp.status_code == 200 and len(resp.text) > 100:
            results.append({
                "vendor": vendor,
                "raw_markdown": clean_markdown_noise(resp.text),
                "link": search_url
            })
    except Exception:
        pass
    return results

async def fetch_shopify(session: httpx.AsyncClient, vendor: str, base_url: str, query: str) -> list[dict]:
    results = []
    api_url = f"{base_url}/search/suggest.json?q={quote_plus(query)}&resources[type]=product&resources[limit]=20"
    try:
        resp = await session.get(api_url, headers=BROWSER_HEADERS, timeout=8.0)
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
                    "raw_desc": BeautifulSoup(p.get("body", ""), "html.parser").get_text(" ", strip=True)[:150]
                })
    except Exception:
        pass

    search_url = f"{base_url}/search?q={quote_plus(query)}"
    try:
        resp = await session.get(f"https://r.jina.ai/{search_url}", headers=BROWSER_HEADERS, timeout=10.0)
        if resp.status_code == 200 and len(resp.text) > 100:
            results.append({
                "vendor": vendor,
                "raw_markdown": clean_markdown_noise(resp.text),
                "link": search_url
            })
    except Exception:
        pass
    return results

async def fetch_custom_and_notion(session: httpx.AsyncClient, vendor: str, target_url: str) -> list[dict]:
    results = []
    try:
        resp = await session.get(f"https://r.jina.ai/{target_url}", headers=BROWSER_HEADERS, timeout=12.0)
        if resp.status_code == 200 and len(resp.text) > 100:
            results.append({
                "vendor": vendor,
                "raw_markdown": clean_markdown_noise(resp.text),
                "link": target_url
            })
    except Exception:
        pass
    return results

async def gather_all_vendors(queries: list[str], selected_vendors: list[str]) -> list[dict]:
    all_raw = []
    primary_query = queries[0]
    async with httpx.AsyncClient(headers=BROWSER_HEADERS, follow_redirects=True) as session:
        tasks = []
        for vendor, url in WOOCOMMERCE_VENDORS.items():
            if vendor in selected_vendors:
                tasks.append(fetch_woocommerce(session, vendor, url, primary_query))

        for vendor, url in SHOPIFY_VENDORS.items():
            if vendor in selected_vendors:
                tasks.append(fetch_shopify(session, vendor, url, primary_query))

        for vendor, search_prefix in CUSTOM_VENDORS.items():
            if vendor in selected_vendors:
                tasks.append(fetch_custom_and_notion(session, vendor, f"{search_prefix}{quote_plus(primary_query)}"))

        if "Danny’s Inventory List" in selected_vendors:
            tasks.append(fetch_custom_and_notion(session, "Danny’s Inventory List", DANNY_NOTION_URL))

        responses = await asyncio.gather(*tasks, return_exceptions=True)
        for r in responses:
            if isinstance(r, list):
                all_raw.extend(r)
    return all_raw

def filter_and_structure_results(
    client: genai.Client,
    model_name: str,
    item_name: str,
    specs: str,
    raw_candidates: list[dict]
) -> list[dict]:
    if not raw_candidates:
        return []
    return fallback_regex_parser(raw_candidates, item_name)

# ----------------- STREAMLIT UI LAYOUT -----------------
st.title("🛸 Indian Drone Vendor Part Finder Agent")
st.caption("Live parallel search across 13 Indian FPV & UAV vendors — Enhanced Robu & Zbotic Bypass")

with st.sidebar:
    st.header("⚙️ Agent Configuration")
    api_key = st.text_input(
        "Gemini API Key",
        value=st.secrets.get("GEMINI_API_KEY", "") if "GEMINI_API_KEY" in st.secrets else "",
        type="password",
        help="Get your free API key from aistudio.google.com"
    )
    selected_model = st.selectbox(
        "Gemini Model",
        options=["gemini-2.0-flash", "gemini-1.5-flash", "gemini-3.0-flash"],
        index=0
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
    item_input = st.text_input("📦 Item Name / Model", placeholder="e.g., Radiomaster Pocket")
with col2:
    spec_input = st.text_input("🔧 Required Specifications (Optional)", placeholder="e.g., ELRS")

if st.button("🔍 Search Across All Vendors", type="primary", use_container_width=True):
    if not api_key:
        st.warning("Please enter your free Gemini API Key in the sidebar.")
    elif not item_input:
        st.warning("Please enter an Item Name to search.")
    else:
        client = genai.Client(api_key=api_key)

        with st.status("Running enhanced multi-vendor search...", expanded=True) as status:
            st.write("🧠 Expanding search terms...")
            search_queries = expand_search_queries(client, selected_model, item_input)
            st.write(f"**Search Variations:** `{', '.join(search_queries)}`")

            st.write(f"🌐 Scraping all {len(selected_vendors)} vendor stores with firewall bypass...")
            raw_data = asyncio.run(gather_all_vendors(search_queries, selected_vendors))
            st.write(f"📥 Collected responses. Parsing full comparison table...")

            matched_items = filter_and_structure_results(client, selected_model, item_input, spec_input, raw_data)
            status.update(label=f"Search complete! Found {len(matched_items)} matching items across vendors.", state="complete")

        if matched_items:
            df = pd.DataFrame(matched_items)
            df = df[df["in_stock"] == True]
            df["_sort_price"] = df["rate"].apply(lambda x: x if x and x > 0 else 9999999)
            df = df.sort_values(by="_sort_price", ascending=True).drop(columns=["_sort_price"]).reset_index(drop=True)

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

            st.subheader(f"📊 Available Products ({len(df_display)} items found — Sorted: Low to High Cost)")
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
            st.info("No matching products found. Try a broader search term.")
