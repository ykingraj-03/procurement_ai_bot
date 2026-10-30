import asyncio
import json
import re
from urllib.parse import quote_plus, unquote
import httpx
from bs4 import BeautifulSoup
import pandas as pd
import streamlit as st

# ----------------- STREAMLIT PAGE CONFIG -----------------
st.set_page_config(
    page_title="DroneScout India | AI Parts Procurement",
    page_icon="🛸",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ----------------- ENGAGING CUSTOM UI CSS -----------------
st.markdown("""
<style>
    /* Main Background & Typography */
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }
    /* Hero Banner */
    .hero-box {
        background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #0f172a 100%);
        border: 1px solid rgba(56, 189, 248, 0.3);
        border-radius: 16px;
        padding: 24px 28px;
        margin-bottom: 20px;
        box-shadow: 0 10px 30px -10px rgba(0, 245, 212, 0.15);
    }
    .hero-title {
        font-size: 2rem;
        font-weight: 800;
        background: linear-gradient(90deg, #00F5D4, #38BDF8, #818CF8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 4px;
    }
    .hero-sub {
        color: #94A3B8;
        font-size: 0.95rem;
        margin: 0;
    }
    /* KPI Metric Cards */
    .kpi-card {
        background: rgba(30, 41, 59, 0.7);
        border: 1px solid rgba(148, 163, 184, 0.2);
        border-left: 4px solid #00F5D4;
        border-radius: 12px;
        padding: 16px 18px;
        height: 100%;
    }
    .kpi-label {
        color: #94A3B8;
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-bottom: 4px;
    }
    .kpi-value {
        color: #F8FAFC;
        font-size: 1.55rem;
        font-weight: 800;
        margin-bottom: 2px;
    }
    .kpi-sub {
        color: #00F5D4;
        font-size: 0.82rem;
        font-weight: 500;
    }
    /* Best Deal Spotlight */
    .best-deal-banner {
        background: linear-gradient(90deg, rgba(16, 185, 129, 0.15) 0%, rgba(15, 23, 42, 0.8) 100%);
        border: 1px solid rgba(16, 185, 129, 0.4);
        border-radius: 12px;
        padding: 14px 20px;
        margin: 16px 0;
        display: flex;
        align-items: center;
        justify-content: space-between;
        flex-wrap: wrap;
        gap: 12px;
    }
    /* Vendor Status Pills */
    .vendor-pill-container {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin: 10px 0 18px 0;
    }
    .vendor-pill-hit {
        background: rgba(16, 185, 129, 0.15);
        border: 1px solid rgba(16, 185, 129, 0.45);
        color: #34D399;
        padding: 4px 12px;
        border-radius: 999px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .vendor-pill-miss {
        background: rgba(51, 65, 85, 0.4);
        border: 1px solid rgba(100, 116, 139, 0.3);
        color: #64748B;
        padding: 4px 12px;
        border-radius: 999px;
        font-size: 0.8rem;
    }
</style>
""", unsafe_allow_html=True)

# ----------------- VENDOR REGISTRY (ALL 13 VENDORS) -----------------
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
    "Indian Robo Store": "https://indianrobostore.com/search?q=",
    "Robokits": "https://robokits.co.in/index.php?main_page=advanced_search_result&keyword=",
    "UAV Marketplace": "https://www.uavmarketplace.in/search?q=",
}

VENDOR_DOMAINS = {
    "Robu": "robu.in",
    "Zbotic": "zbotic.in",
    "Tujo RC": "tujorc.com",
    "Quadkart": "quadkart.in",
    "Design Info": "designinfo.in",
    "Anubis Tech": "anubisrc.com",
    "FPV Guru": "fpvguru.in",
    "Hi Tech XYZ": "hitechxyz.in",
    "Xrobo": "xrobo.in",
    "Indian Robo Store": "indianrobostore.com",
    "Robokits": "robokits.co.in",
    "UAV Marketplace": "uavmarketplace.in",
}

DANNY_NOTION_URL = "https://danny8.notion.site/Danny-s-Inventory-List-214fd82319444160b57ffdf5ebb118bd"

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}

KNOWN_BRANDS = [
    "RadioMaster", "SpeedyBee", "T-Motor", "Hobbywing", "Holybro", "GEPRC",
    "Caddx", "BetaFPV", "Foxeer", "RushFPV", "Flywoo", "iFlight", "HGLRC",
    "Matek", "Skyzone", "Emax", "Diatone", "Gemfan", "HQProp", "Walksnail",
    "DJI", "SIYI", "Skydroid", "CubePilot", "Tarot", "SunnySky", "CNHL",
    "Ovonic", "Tattu", "BrotherHobby", "RCINPower", "TBS", "ImmersionRC",
    "JHEMCU", "DarwinFPV", "Happymodel", "AxisFlying", "MicoAir", "Radiolink",
    "Flysky", "FrSky", "SkyRC", "ToolkitRC", "ISDT", "RunCam", "Hawkeye"
]

ACCESSORY_KEYWORDS = {
    "case", "cases", "shell", "strap", "neck strap", "button", "switch",
    "screw", "screws", "spare", "replacement", "cable", "wire", "harness",
    "mount", "bracket", "cap", "cover", "protector", "screen protector",
    "sticker", "spring", "springs", "stick end", "stick ends", "pouch",
    "bag", "arm", "spare arm", "bell", "shaft", "bearing", "pad", "nut",
    "o-ring", "silicone", "sponge", "foam", "lens cap", "decal"
}

SYNONYM_MAP = {
    "elrs": ["elrs", "expresslrs"],
    "expresslrs": ["elrs", "expresslrs"],
    "fc": ["fc", "flight controller", "f405", "f722", "h743"],
    "esc": ["esc", "speed controller", "4in1", "4-in-1", "blheli"],
    "rx": ["rx", "receiver"],
    "tx": ["tx", "transmitter", "radio", "controller"],
    "vtx": ["vtx", "video transmitter"],
}

# ----------------- INTELLIGENT RELEVANCE & SPEC ENGINE -----------------
def get_query_tokens(query: str) -> list[str]:
    clean = re.sub(r"[^a-zA-Z0-9\.]", " ", query.lower())
    stop_words = {"for", "with", "and", "the", "in", "of", "to", "a", "an", "drone", "fpv", "rc"}
    tokens = [t for t in clean.split() if len(t) >= 2 and t not in stop_words]
    return tokens if tokens else clean.split()

def is_relevant_product(title: str, query: str, exclude_accessories: bool = True) -> tuple[bool, int]:
    """
    Checks if a product title genuinely matches the user's search words.
    Returns (is_match, relevance_score).
    """
    if not title or len(title.strip()) < 5:
        return False, 0

    title_lower = title.lower()
    query_lower = query.lower().strip()

    # Reject obvious website navigation labels
    nav_exact = {
        "home", "shop", "cart", "view cart", "add to cart", "checkout", "my account",
        "login", "register", "wishlist", "compare", "track order", "contact us",
        "about us", "privacy policy", "terms and conditions", "read more", "search"
    }
    if title_lower.strip() in nav_exact:
        return False, 0

    tokens = get_query_tokens(query)
    if not tokens:
        return False, 0

    # Check how many query tokens match the title (with synonym & spacing tolerance)
    matched_count = 0
    title_compact = re.sub(r"[\s\-_]", "", title_lower)

    for tok in tokens:
        synonyms = SYNONYM_MAP.get(tok, [tok])
        tok_matched = False
        for syn in synonyms:
            syn_compact = re.sub(r"[\s\-_]", "", syn)
            if syn in title_lower or syn_compact in title_compact:
                tok_matched = True
                break
        if tok_matched:
            matched_count += 1

    # Strictness rule:
    # - 1 or 2 tokens: ALL tokens must match (100% match)
    # - 3+ tokens: at least (N - 1) tokens must match, and the first token MUST match
    if len(tokens) <= 2:
        if matched_count < len(tokens):
            return False, 0
    else:
        first_tok_syns = SYNONYM_MAP.get(tokens[0], [tokens[0]])
        first_matched = any(s in title_lower or s in title_compact for s in first_tok_syns)
        if not first_matched or matched_count < len(tokens) - 1:
            return False, 0

    # Accessory filtering (unless user explicitly searched for an accessory word)
    if exclude_accessories:
        user_wants_accessory = any(acc in query_lower for acc in ACCESSORY_KEYWORDS)
        if not user_wants_accessory:
            for acc in ACCESSORY_KEYWORDS:
                if re.search(rf"\b{re.escape(acc)}\b", title_lower):
                    return False, 0

    # Calculate relevance score
    score = matched_count * 25
    if query_lower in title_lower:
        score += 40
    if title_lower.startswith(tokens[0]):
        score += 15
    return True, score

def detect_brand(title: str, default_brand: str = "") -> str:
    if default_brand and default_brand.lower() not in ["generic", "unknown", "n/a", ""]:
        return default_brand
    title_lower = title.lower()
    for brand in KNOWN_BRANDS:
        if brand.lower() in title_lower:
            return brand
    # Fallback to first capitalized word
    first_word = title.strip().split()[0] if title.strip() else "Generic"
    return first_word if len(first_word) > 2 else "Generic"

def extract_specs_from_title(title: str, extra_desc: str = "") -> str:
    combined = f"{title} {extra_desc}"
    spec_patterns = [
        r"\b\d{3,4}\s*KV\b",
        r"\b\d{1,3}A\b",
        r"\b[1-8]S\b",
        r"\b2\.4\s*G(?:Hz)?\b",
        r"\b5\.8\s*G(?:Hz)?\b",
        r"\b915\s*MHz\b",
        r"\b868\s*MHz\b",
        r"\bELRS\b|\bExpressLRS\b",
        r"\bCC2500\b|\b4-in-1\b|\b4in1\b",
        r"\bF405\b|\bF722\b|\bH743\b|\bF4\b|\bF7\b",
        r"\b\d+(?:\.\d+)?\s*(?:Inch|inch|\")\b",
        r"\b\d{3,4}\s*mAh\b",
        r"\b\d{2,4}\s*mW\b|\b\d+(?:\.\d+)?\s*W\b",
        r"\bM10\b|\bM8N\b|\bHall\s*Gimbal\b|\bEdgeTX\b",
        r"\bCharcoal\b|\bTransparent\b|\bCrush\b|\bMode\s*[12]\b|\bM2\b"
    ]
    found = []
    for pat in spec_patterns:
        for m in re.findall(pat, combined, re.I):
            clean_m = m.strip()
            if clean_m.upper() not in [x.upper() for x in found]:
                found.append(clean_m)
    if found:
        return " • ".join(found[:6])
    return extra_desc[:90].strip() if extra_desc else "Standard Spec"

def parse_inr_price(text: str) -> float:
    """Extracts the primary selling price in INR from strings like '₹ 10,399(Incl. GST)' or '₹7504₹13539'."""
    if not text:
        return 0.0
    # Match ₹ or Rs followed by digits
    matches = re.findall(r"(?:₹|Rs\.?|INR)\s*([0-9,]+(?:\.[0-9]{1,2})?)", text, re.I)
    valid_prices = []
    for m in matches:
        try:
            val = float(m.replace(",", ""))
            if 15 <= val <= 500000:
                valid_prices.append(val)
        except ValueError:
            pass
    if valid_prices:
        # On Indian stores, when two prices are shown side by side (e.g. Sale vs MRP, or Excl GST vs Incl GST):
        # If Zbotic format: '₹9,438.82 ( ₹7,999.00 + GST)', first price is Incl GST.
        return valid_prices[0]
    return 0.0

# ----------------- UNIVERSAL MARKDOWN & HTML PARSERS -----------------
def parse_markdown_listing(md_text: str, vendor: str, base_url: str, query: str, exclude_accessories: bool) -> list[dict]:
    """
    Parses Jina Reader markdown from Robu, Zbotic, Indian Robo Store, Quadkart, Design Info, UAV Marketplace, etc.
    Specifically handles Robu's '##### SKU: R180124' and Zbotic's 'SKU: AI7233' layouts.
    """
    items = []
    lines = [l.strip() for l in md_text.splitlines() if l.strip()]

    for i, line in enumerate(lines):
        # Match markdown links: [Product Title](https://...)
        for m in re.finditer(r"\[([^\[\]]+)\]\((https?://[^\s\)]+)\)", line):
            raw_title = m.group(1).strip()
            url = m.group(2).strip()

            # Clean markdown formatting from title
            clean_title = re.sub(r"^(?:####+|###+|\*+|\-+)\s*", "", raw_title).strip()
            # Strip trailing price/cart text if wrapped inside the same link
            clean_title = re.sub(r"(?:Add to cart|Add to Wishlist|Add to Compare|Quick View).*$", "", clean_title, flags=re.I).strip()

            if any(skip_u in url.lower() for skip_u in [
                "facebook.com", "instagram.com", "twitter.com", "linkedin.com", "youtube.com",
                "/cart", "/checkout", "/my-account", "/login", "/wishlist", "add-to-cart=",
                "/category/", "/product-category/", "/tag/", "/blog/", "javascript:"
            ]):
                continue

            is_match, score = is_relevant_product(clean_title, query, exclude_accessories)
            if not is_match:
                continue

            # Inspect context window (2 lines above and 6 lines below) for SKU, Price, and Stock status
            start_idx = max(0, i - 1)
            end_idx = min(len(lines), i + 7)
            window_lines = []
            for j in range(start_idx, end_idx):
                # Stop window if we hit the next product heading
                if j > i and re.search(r"^#{2,5}\s*\[", lines[j]):
                    break
                window_lines.append(lines[j])
            window_blob = " \n ".join(window_lines)

            # Check Out of Stock in window
            if re.search(r"out of stock|sold out|currently unavailable", window_blob, re.I):
                continue

            # Extract SKU (e.g., 'SKU: R180124', 'SKU: AI7233', 'SKU: 12640088')
            sku_match = re.search(r"SKU\s*[:#\-]?\s*([A-Za-z0-9_\-]+)", window_blob, re.I)
            sku = sku_match.group(1).strip() if sku_match else "N/A"

            # Extract Price
            price = parse_inr_price(window_blob)

            items.append({
                "product_name": clean_title,
                "specification": extract_specs_from_title(clean_title, window_blob),
                "brand_name": detect_brand(clean_title),
                "vendor_name": vendor,
                "sku_name": sku,
                "rate": price,
                "in_stock": True,
                "link": url,
                "relevance": score
            })
    return items

def parse_html_dom(html_text: str, vendor: str, base_url: str, query: str, exclude_accessories: bool) -> list[dict]:
    """Direct BeautifulSoup parser for WooCommerce, ZenCart (Robokits), and Custom stores."""
    items = []
    soup = BeautifulSoup(html_text, "html.parser")

    # Select common e-commerce product cards
    cards = soup.select(
        ".product, li.product, .product-grid-item, .type-product, "
        ".product-item, .product-card, .product-layout, .productListing-odd, .productListing-even"
    )

    for card in cards:
        card_text = card.get_text(" ", strip=True)
        if re.search(r"out of stock|sold out", card_text, re.I) or "out-of-stock" in " ".join(card.get("class", [])):
            continue

        # Find title element
        title_el = card.select_one(
            ".woocommerce-loop-product__title, .product-title, .name, "
            "h2 a, h3 a, h4 a, h2, h3, h4, a.woocommerce-LoopProduct-link"
        )
        if not title_el:
            continue
        title = title_el.get_text(" ", strip=True)

        is_match, score = is_relevant_product(title, query, exclude_accessories)
        if not is_match:
            continue

        # Find product link
        a_tag = title_el if title_el.name == "a" else card.select_one("a[href]")
        link = a_tag["href"] if a_tag and a_tag.has_attr("href") else base_url
        if link.startswith("/"):
            link = f"{base_url.rstrip('/')}{link}"

        # Extract SKU if present
        sku_el = card.select_one(".sku, .product-sku")
        if sku_el:
            sku = sku_el.get_text(strip=True).replace("SKU:", "").strip()
        else:
            sku_m = re.search(r"SKU\s*[:#\-]?\s*([A-Za-z0-9_\-]+)", card_text, re.I)
            sku = sku_m.group(1) if sku_m else "N/A"

        # Extract Price (prefer <ins> sale price over <del> regular price)
        ins_el = card.select_one("ins .amount, . price ins, .specialPrice, .sale-price")
        price_el = ins_el or card.select_one(".price, .product-price, .amount")
        price_val = parse_inr_price(price_el.get_text(" ", strip=True) if price_el else card_text)

        items.append({
            "product_name": title,
            "specification": extract_specs_from_title(title, card_text),
            "brand_name": detect_brand(title),
            "vendor_name": vendor,
            "sku_name": sku,
            "rate": price_val,
            "in_stock": True,
            "link": link,
            "relevance": score
        })
    return items

# ----------------- MULTI-LAYER ASYNC VENDOR SCRAPERS -----------------
async def fetch_via_jina(session: httpx.AsyncClient, jina_sem: asyncio.Semaphore, target_url: str) -> str:
    """Throttled Jina Reader fetcher so burst requests never trigger 429 rate limits."""
    async with jina_sem:
        try:
            resp = await session.get(
                f"https://r.jina.ai/{target_url}",
                headers={**BROWSER_HEADERS, "X-Return-Format": "markdown"},
                timeout=14.0
            )
            if resp.status_code == 200 and len(resp.text) > 120:
                return resp.text
        except Exception:
            pass
    return ""

async def fetch_ddg_vendor_fallback(
    session: httpx.AsyncClient,
    vendor: str,
    domain: str,
    query: str,
    exclude_accessories: bool
) -> list[dict]:
    """
    Fallback discovery via DuckDuckGo HTML search for stores behind strict Cloudflare firewalls (like Robu/Zbotic).
    """
    items = []
    ddg_query = f"site:{domain} {query}"
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(ddg_query)}"
    try:
        resp = await session.get(url, headers=BROWSER_HEADERS, timeout=10.0)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for res in soup.select(".result"):
                a_el = res.select_one(".result__a")
                snip_el = res.select_one(".result__snippet")
                if not a_el:
                    continue
                raw_title = a_el.get_text(" ", strip=True)
                # Strip trailing store name from search engine title
                clean_title = re.split(r"\s+[\-\|–]\s+(?:Buy|Robu|Zbotic|Quadkart|Design Info|Indian Robo|Robokits|Xrobo)", raw_title, flags=re.I)[0].strip()

                href = a_el.get("href", "")
                if "uddg=" in href:
                    href = unquote(href.split("uddg=")[1].split("&")[0])

                if any(skip in href.lower() for skip in ["/category/", "/product-category/", "/tag/", "/blog/", "/brand/"]):
                    continue

                snippet = snip_el.get_text(" ", strip=True) if snip_el else ""
                combined_blob = f"{clean_title} {snippet}"

                if re.search(r"out of stock|sold out", combined_blob, re.I):
                    continue

                is_match, score = is_relevant_product(clean_title, query, exclude_accessories)
                if not is_match:
                    continue

                sku_m = re.search(r"SKU\s*[:#\-]?\s*([A-Za-z0-9_\-]+)", combined_blob, re.I)
                sku = sku_m.group(1) if sku_m else "N/A"
                price = parse_inr_price(combined_blob)

                items.append({
                    "product_name": clean_title,
                    "specification": extract_specs_from_title(clean_title, snippet),
                    "brand_name": detect_brand(clean_title),
                    "vendor_name": vendor,
                    "sku_name": sku,
                    "rate": price,
                    "in_stock": True,
                    "link": href,
                    "relevance": score
                })
    except Exception:
        pass
    return items

async def scrape_woocommerce_vendor(
    session: httpx.AsyncClient,
    jina_sem: asyncio.Semaphore,
    vendor: str,
    base_url: str,
    query: str,
    exclude_accessories: bool
) -> list[dict]:
    found_items = []

    # Layer 1: WooCommerce Store REST API (ONLY keep items that pass relevance check!)
    api_url = f"{base_url}/wp-json/wc/store/v1/products?search={quote_plus(query)}&per_page=25"
    try:
        resp = await session.get(api_url, timeout=8.0)
        if resp.status_code == 200 and "application/json" in resp.headers.get("content-type", ""):
            data = resp.json()
            if isinstance(data, list):
                for item in data:
                    if not item.get("is_in_stock", True):
                        continue
                    title = BeautifulSoup(item.get("name", ""), "html.parser").get_text(" ", strip=True)
                    is_match, score = is_relevant_product(title, query, exclude_accessories)
                    if not is_match:
                        continue
                    prices = item.get("prices", {})
                    raw_price = prices.get("price", "0")
                    minor_unit = prices.get("currency_minor_unit", 2)
                    price_val = float(raw_price) / (10 ** minor_unit) if raw_price else 0.0
                    short_desc = BeautifulSoup(item.get("short_description", ""), "html.parser").get_text(" ", strip=True)
                    found_items.append({
                        "product_name": title,
                        "specification": extract_specs_from_title(title, short_desc),
                        "brand_name": detect_brand(title),
                        "vendor_name": vendor,
                        "sku_name": item.get("sku") or "N/A",
                        "rate": price_val,
                        "in_stock": True,
                        "link": item.get("permalink", base_url),
                        "relevance": score
                    })
    except Exception:
        pass

    if found_items:
        return found_items

    # Layer 2: Direct HTML Search Page
    search_url = f"{base_url}/?s={quote_plus(query)}&post_type=product"
    try:
        resp = await session.get(search_url, timeout=9.0)
        if resp.status_code == 200 and len(resp.text) > 500:
            found_items.extend(parse_html_dom(resp.text, vendor, base_url, query, exclude_accessories))
    except Exception:
        pass

    if found_items:
        return found_items

    # Layer 3: Throttled Jina Reader (Essential for Robu & Zbotic Cloudflare pages)
    md_text = await fetch_via_jina(session, jina_sem, search_url)
    if md_text:
        found_items.extend(parse_markdown_listing(md_text, vendor, base_url, query, exclude_accessories))

    # Layer 4: DuckDuckGo Site-Search Fallback if Cloudflare blocked both direct and Jina
    if not found_items and vendor in VENDOR_DOMAINS:
        found_items.extend(await fetch_ddg_vendor_fallback(session, vendor, VENDOR_DOMAINS[vendor], query, exclude_accessories))

    return found_items

async def scrape_shopify_vendor(
    session: httpx.AsyncClient,
    jina_sem: asyncio.Semaphore,
    vendor: str,
    base_url: str,
    query: str,
    exclude_accessories: bool
) -> list[dict]:
    found_items = []
    api_url = f"{base_url}/search/suggest.json?q={quote_plus(query)}&resources[type]=product&resources[limit]=20"
    try:
        resp = await session.get(api_url, timeout=8.0)
        if resp.status_code == 200:
            data = resp.json()
            products = data.get("resources", {}).get("results", {}).get("products", [])
            for p in products:
                if not p.get("available", True):
                    continue
                title = p.get("title", "")
                is_match, score = is_relevant_product(title, query, exclude_accessories)
                if not is_match:
                    continue
                body_text = BeautifulSoup(p.get("body", ""), "html.parser").get_text(" ", strip=True)
                sku = p.get("variants", [{}])[0].get("sku") if p.get("variants") else "N/A"
                found_items.append({
                    "product_name": title,
                    "specification": extract_specs_from_title(title, body_text),
                    "brand_name": detect_brand(title, p.get("vendor", "")),
                    "vendor_name": vendor,
                    "sku_name": sku if sku else "N/A",
                    "rate": float(p.get("price", 0)),
                    "in_stock": True,
                    "link": f"{base_url}{p.get('url', '')}",
                    "relevance": score
                })
    except Exception:
        pass

    if not found_items:
        search_url = f"{base_url}/search?q={quote_plus(query)}"
        md_text = await fetch_via_jina(session, jina_sem, search_url)
        if md_text:
            found_items.extend(parse_markdown_listing(md_text, vendor, base_url, query, exclude_accessories))

    if not found_items and vendor in VENDOR_DOMAINS:
        found_items.extend(await fetch_ddg_vendor_fallback(session, vendor, VENDOR_DOMAINS[vendor], query, exclude_accessories))

    return found_items

async def scrape_custom_or_notion_vendor(
    session: httpx.AsyncClient,
    jina_sem: asyncio.Semaphore,
    vendor: str,
    target_url: str,
    query: str,
    exclude_accessories: bool
) -> list[dict]:
    found_items = []
    # Try direct HTML first (works well on Robokits & Indian Robo Store)
    if vendor != "Danny’s Inventory List":
        try:
            resp = await session.get(target_url, timeout=9.0)
            if resp.status_code == 200 and len(resp.text) > 500:
                found_items.extend(parse_html_dom(resp.text, vendor, target_url, query, exclude_accessories))
        except Exception:
            pass

    if not found_items:
        md_text = await fetch_via_jina(session, jina_sem, target_url)
        if md_text:
            found_items.extend(parse_markdown_listing(md_text, vendor, target_url, query, exclude_accessories))

    if not found_items and vendor in VENDOR_DOMAINS:
        found_items.extend(await fetch_ddg_vendor_fallback(session, vendor, VENDOR_DOMAINS[vendor], query, exclude_accessories))

    return found_items

async def run_all_scrapers(query: str, selected_vendors: list[str], exclude_accessories: bool) -> list[dict]:
    jina_sem = asyncio.Semaphore(3)  # Prevents Jina Reader 429 burst blocks
    all_items = []

    async with httpx.AsyncClient(headers=BROWSER_HEADERS, follow_redirects=True) as session:
        tasks = []
        for vendor, url in WOOCOMMERCE_VENDORS.items():
            if vendor in selected_vendors:
                tasks.append(scrape_woocommerce_vendor(session, jina_sem, vendor, url, query, exclude_accessories))

        for vendor, url in SHOPIFY_VENDORS.items():
            if vendor in selected_vendors:
                tasks.append(scrape_shopify_vendor(session, jina_sem, vendor, url, query, exclude_accessories))

        for vendor, search_prefix in CUSTOM_VENDORS.items():
            if vendor in selected_vendors:
                tasks.append(scrape_custom_or_notion_vendor(
                    session, jina_sem, vendor, f"{search_prefix}{quote_plus(query)}", query, exclude_accessories
                ))

        if "Danny’s Inventory List" in selected_vendors:
            tasks.append(scrape_custom_or_notion_vendor(
                session, jina_sem, "Danny’s Inventory List", DANNY_NOTION_URL, query, exclude_accessories
            ))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in results:
            if isinstance(res, list):
                all_items.extend(res)

    # Deduplicate by normalized URL and (Vendor + Title)
    seen_keys = set()
    unique_items = []
    for item in all_items:
        clean_link = item["link"].split("?")[0].rstrip("/")
        dedup_key = (item["vendor_name"], item["product_name"].lower().strip(), clean_link)
        if dedup_key not in seen_keys and clean_link not in seen_keys:
            seen_keys.add(dedup_key)
            seen_keys.add(clean_link)
            unique_items.append(item)

    return unique_items

# ----------------- SIDEBAR CONFIGURATION -----------------
with st.sidebar:
    st.markdown("### ⚙️ Control Center")
    all_vendor_names = (
        list(WOOCOMMERCE_VENDORS.keys())
        + list(SHOPIFY_VENDORS.keys())
        + list(CUSTOM_VENDORS.keys())
        + ["Danny’s Inventory List"]
    )
    selected_vendors = st.multiselect(
        "🏪 Active Indian Vendors (13)",
        options=all_vendor_names,
        default=all_vendor_names
    )
    st.divider()
    st.markdown("### 🎯 Search Precision")
    exclude_accessories = st.toggle(
        "Exclude Spare Parts & Cases",
        value=True,
        help="Filters out cheap accessories (straps, buttons, cases, screws) unless you explicitly include those words in your search."
    )
    hide_unpriced = st.toggle(
        "Hide Items Without Listed Price",
        value=False,
        help="Only show listings where a numeric INR price was found."
    )

# ----------------- HERO HEADER -----------------
st.markdown("""
<div class="hero-box">
    <div class="hero-title">🛸 DroneScout India — Multi-Vendor Parts Command Center</div>
    <p class="hero-sub">Live parallel inventory & price comparison across 13 Indian FPV, RC & UAV hardware stores</p>
</div>
""", unsafe_allow_html=True)

# ----------------- SINGLE SEARCH BOX & QUICK CHIPS -----------------
if "search_query" not in st.session_state:
    st.session_state.search_query = ""

def set_quick_query(q: str):
    st.session_state.search_query = q

# Quick-Select Chips
chip_cols = st.columns([1.2, 1.5, 1.5, 1.4, 1.3, 1.3, 1.2])
chip_cols[0].caption("⚡ Quick Test:")
if chip_cols[1].button("🎮 RadioMaster Pocket", use_container_width=True):
    set_quick_query("Radiomaster Pocket")
if chip_cols[2].button("⚡ SpeedyBee F405 V4", use_container_width=True):
    set_quick_query("SpeedyBee F405 V4")
if chip_cols[3].button("🔄 2207 Motor", use_container_width=True):
    set_quick_query("2207 Motor")
if chip_cols[4].button("📡 ELRS Receiver", use_container_width=True):
    set_quick_query("ELRS Receiver")
if chip_cols[5].button("🛸 Mark4 Frame", use_container_width=True):
    set_quick_query("Mark4 Frame")
if chip_cols[6].button("🧭 M10 GPS", use_container_width=True):
    set_quick_query("M10 GPS")

# Single Search Input Bar
search_col, btn_col = st.columns([4, 1])
with search_col:
    query_input = st.text_input(
        "🔍 Search Drone Part, Model, or Keyword",
        value=st.session_state.search_query,
        placeholder="Type part name (e.g., Radiomaster Pocket, SpeedyBee F405 V4, 2207 1950KV, Skyzone Cobra X)...",
        label_visibility="collapsed"
    )
with btn_col:
    trigger_search = st.button("🚀 Scan 13 Vendors", type="primary", use_container_width=True)

# ----------------- EXECUTION & ENGAGING DASHBOARD -----------------
if trigger_search or (query_input and query_input != st.session_state.get("_last_ran_query", "")):
    if not query_input.strip():
        st.warning("Please enter a drone part name in the search box above.")
    else:
        st.session_state._last_ran_query = query_input
        with st.status(f"🔎 Scanning {len(selected_vendors)} Indian drone stores for **'{query_input}'**...", expanded=False) as status:
            matched_items = asyncio.run(run_all_scrapers(query_input.strip(), selected_vendors, exclude_accessories))
            status.update(
                label=f"✅ Scan complete! Found {len(matched_items)} relevant in-stock listings for '{query_input}'.",
                state="complete"
            )

        st.session_state["last_results"] = matched_items

# Render Results if Available
results_list = st.session_state.get("last_results", [])

if results_list:
    df = pd.DataFrame(results_list)
    if hide_unpriced:
        df = df[df["rate"] > 0]

    if not df.empty:
        # Sort strictly from Low to High Rate (put rate == 0 at the bottom)
        df["_sort_rate"] = df["rate"].apply(lambda r: r if r and r > 0 else 9999999.0)
        df = df.sort_values(by=["_sort_rate", "relevance"], ascending=[True, False]).drop(columns=["_sort_rate"]).reset_index(drop=True)

        # Calculate KPI metrics
        priced_df = df[df["rate"] > 0]
        if not priced_df.empty:
            lowest_row = priced_df.iloc[0]
            lowest_price = f"₹{lowest_row['rate']:,.2f}"
            lowest_vendor = lowest_row["vendor_name"]
            highest_price = priced_df["rate"].max()
            savings = highest_price - lowest_row["rate"]
            spread_text = f"Save up to ₹{savings:,.0f}" if savings > 0 else "Uniform pricing"
        else:
            lowest_price = "Check Store"
            lowest_vendor = df.iloc[0]["vendor_name"]
            spread_text = "Click link for price"

        vendors_with_stock = df["vendor_name"].nunique()
        vendor_counts = df["vendor_name"].value_counts().to_dict()

        # 1. KPI METRIC CARDS
        k1, k2, k3, k4 = st.columns(4)
        k1.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">🏆 Lowest Rate Found</div>
            <div class="kpi-value">{lowest_price}</div>
            <div class="kpi-sub">Best deal on {lowest_vendor}</div>
        </div>
        """, unsafe_allow_html=True)

        k2.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">📦 In-Stock Matches</div>
            <div class="kpi-value">{len(df)} Items</div>
            <div class="kpi-sub">Verified relevant matches</div>
        </div>
        """, unsafe_allow_html=True)

        k3.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">🏪 Vendor Availability</div>
            <div class="kpi-value">{vendors_with_stock} / {len(selected_vendors)} Stores</div>
            <div class="kpi-sub">Active stores carrying stock</div>
        </div>
        """, unsafe_allow_html=True)

        k4.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">💰 Price Spread</div>
            <div class="kpi-value">{spread_text}</div>
            <div class="kpi-sub">Sorted Lowest → Highest</div>
        </div>
        """, unsafe_allow_html=True)

        # 2. LIVE VENDOR COVERAGE PILLS
        pills_html = '<div class="vendor-pill-container">'
        for v in selected_vendors:
            cnt = vendor_counts.get(v, 0)
            if cnt > 0:
                pills_html += f'<span class="vendor-pill-hit">🟢 {v} ({cnt})</span>'
            else:
                pills_html += f'<span class="vendor-pill-miss">⚪ {v} (0)</span>'
        pills_html += '</div>'
        st.markdown(pills_html, unsafe_allow_html=True)

        # 3. BEST DEAL SPOTLIGHT BANNER
        if not priced_df.empty:
            best = priced_df.iloc[0]
            st.markdown(f"""
            <div class="best-deal-banner">
                <div>
                    <span style="color:#10B981; font-weight:700; font-size:0.85rem;">⚡ CHEAPEST IN-STOCK OPTION:</span>
                    <div style="color:#F8FAFC; font-size:1.1rem; font-weight:700;">{best['product_name']}</div>
                    <div style="color:#94A3B8; font-size:0.85rem;">Vendor: <b>{best['vendor_name']}</b> | Brand: <b>{best['brand_name']}</b> | SKU: <b>{best['sku_name']}</b></div>
                </div>
                <div style="text-align:right;">
                    <div style="color:#00F5D4; font-size:1.4rem; font-weight:800;">₹{best['rate']:,.2f}</div>
                    <a href="{best['link']}" target="_blank" style="color:#38BDF8; text-decoration:none; font-weight:600; font-size:0.9rem;">Open Product Page ↗</a>
                </div>
            </div>
            """, unsafe_allow_html=True)

        # 4. INSTANT FILTER BAR
        fcol1, fcol2 = st.columns([2, 2])
        with fcol1:
            vendor_filter = st.multiselect(
                "Filter Table by Vendor",
                options=sorted(df["vendor_name"].unique().tolist()),
                default=sorted(df["vendor_name"].unique().tolist())
            )
        with fcol2:
            brand_filter = st.multiselect(
                "Filter Table by Brand",
                options=sorted(df["brand_name"].unique().tolist()),
                default=sorted(df["brand_name"].unique().tolist())
            )

        filtered_df = df[df["vendor_name"].isin(vendor_filter) & df["brand_name"].isin(brand_filter)].reset_index(drop=True)

        # Format exact requested columns
        df_display = filtered_df[[
            "product_name", "specification", "brand_name",
            "vendor_name", "sku_name", "rate", "link"
        ]].rename(columns={
            "product_name": "Product Name",
            "specification": "Specification",
            "brand_name": "Brand Name",
            "vendor_name": "Vendor Name",
            "sku_name": "SKU Name",
            "rate": "Rate (₹)",
            "link": "Link"
        })

        # 5. MAIN INTERACTIVE COMPARISON TABLE
        st.subheader(f"📊 Price Comparison Table ({len(df_display)} Matching Products — Low to High)")
        st.dataframe(
            df_display,
            column_config={
                "Product Name": st.column_config.TextColumn("Product Name", width="large"),
                "Specification": st.column_config.TextColumn("Specification", width="medium"),
                "Brand Name": st.column_config.TextColumn("Brand Name", width="small"),
                "Vendor Name": st.column_config.TextColumn("Vendor Name", width="small"),
                "SKU Name": st.column_config.TextColumn("SKU Name", width="small"),
                "Rate (₹)": st.column_config.NumberColumn("Rate (₹)", format="₹%.2f"),
                "Link": st.column_config.LinkColumn("Link", display_text="Buy / View ↗")
            },
            use_container_width=True,
            hide_index=True,
            height=min(650, 55 + len(df_display) * 38)
        )

        # CSV Download Button
        csv_bytes = df_display.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 Download Full Comparison Sheet (CSV)",
            data=csv_bytes,
            file_name=f"dronescout_{query_input.strip().replace(' ', '_')}.csv",
            mime="text/csv"
        )
elif "last_results" in st.session_state:
    st.info("No matching in-stock items found across the selected vendors. Try searching with a shorter model keyword (e.g., 'Pocket' or 'F405') or toggle off 'Exclude Spare Parts & Cases' in the sidebar.")
