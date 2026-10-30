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
        if not first_matched or matched_count < len
