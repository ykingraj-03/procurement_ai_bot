import asyncio
import io
import json
import re
import zipfile
from urllib.parse import quote_plus, unquote
from xml.sax.saxutils import escape
import httpx
from bs4 import BeautifulSoup
import pandas as pd
import streamlit as st

try:
    from google import genai
    from google.genai import types
    from pydantic import BaseModel, Field
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

# ----------------- PAGE CONFIG -----------------
st.set_page_config(
    page_title="DroneProcurement — Smart Sourcing & BOQ Builder",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ----------------- MINIMALIST LIGHT PALETTE CSS -----------------
st.markdown("""
<style>
    /* Force Clean Minimalist Light Theme */
    .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        background-color: #F8FAFC !important;
        color: #0F172A !important;
    }
    [data-testid="stSidebar"] {
        background-color: #FFFFFF !important;
        border-right: 1px solid #E2E8F0 !important;
    }
    .block-container {
        max-width: 1280px;
        padding-top: 2rem;
        padding-bottom: 3rem;
    }
    /* Minimalist Header */
    .app-header {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 20px 24px;
        margin-bottom: 20px;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
    }
    .app-title {
        font-size: 1.5rem;
        font-weight: 700;
        color: #0F172A;
        margin: 0 0 4px 0;
        letter-spacing: -0.02em;
    }
    .app-subtitle {
        font-size: 0.9rem;
        color: #64748B;
        margin: 0;
    }
    /* Intent Recognition Bar */
    .intent-bar {
        background: #F1F5F9;
        border: 1px solid #CBD5E1;
        border-radius: 8px;
        padding: 10px 16px;
        margin: 12px 0 20px 0;
        font-size: 0.85rem;
        color: #334155;
        display: flex;
        flex-wrap: wrap;
        gap: 16px;
        align-items: center;
    }
    .intent-badge {
        background: #FFFFFF;
        border: 1px solid #CBD5E1;
        color: #0F172A;
        padding: 2px 10px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.8rem;
    }
    /* Section Cards */
    .section-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 24px;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.02);
    }
    .section-title {
        font-size: 1.1rem;
        font-weight: 600;
        color: #0F172A;
        margin-bottom: 4px;
    }
    .section-note {
        font-size: 0.83rem;
        color: #64748B;
        margin-bottom: 14px;
    }
    /* Metric Summary Pills */
    .summary-strip {
        display: flex;
        gap: 12px;
        flex-wrap: wrap;
        margin-bottom: 14px;
    }
    .summary-pill {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 8px 14px;
        font-size: 0.84rem;
        color: #475569;
    }
    .summary-pill b {
        color: #0F172A;
    }
    /* Input & Button Polish */
    .stTextInput input {
        background-color: #FFFFFF !important;
        color: #0F172A !important;
        border: 1px solid #CBD5E1 !important;
        border-radius: 8px !important;
    }
    .stButton > button[kind="primary"] {
        background-color: #2563EB !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
    }
    .stButton > button[kind="secondary"] {
        background-color: #FFFFFF !important;
        color: #0F172A !important;
        border: 1px solid #CBD5E1 !important;
        border-radius: 8px !important;
        font-weight: 500 !important;
    }
</style>
""", unsafe_allow_html=True)

# ----------------- VENDOR REGISTRY (13 INDIAN VENDORS) -----------------
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

# ----------------- EXPANDED INDIAN & GLOBAL DRONE BRANDS (185+ BRANDS) -----------------
KNOWN_BRANDS = [
    # Indian Domestic & Store OEMs
    "ZeroDrag", "Vimana", "Drakmatter", "Orange", "Bonka", "ProRange",
    "Garuda", "Quadkart", "Robokits", "Robu", "Drona Aviation", "Skykrafts",
    # Major FPV & RC Ecosystems
    "RadioMaster", "SpeedyBee", "T-Motor", "T-Hobby", "Hobbywing", "Holybro",
    "GEPRC", "Caddx", "CaddxFPV", "Walksnail", "BetaFPV", "Foxeer", "RushFPV",
    "Flywoo", "iFlight", "HGLRC", "Matek", "MatekSys", "Skyzone", "Emax",
    "Diatone", "Mamba", "Gemfan", "HQProp", "DJI", "SIYI", "Skydroid",
    "Herelink", "CubePilot", "HEX", "ProfiCNC", "CUAV", "Tarot", "SunnySky",
    # Batteries, Li-Ion Cells & Chargers
    "CNHL", "Ovonic", "Tattu", "Gens Ace", "GNB", "Gaoneng", "Herewin",
    "Auline", "Dogcom", "Zeee", "Turnigy", "Zippy", "Infinity", "Lava",
    "Molicel", "Murata", "Samsung", "Panasonic", "Vapcell", "LG Chem",
    "ToolkitRC", "ISDT", "HOTA", "SkyRC", "UltraPower", "Sequre", "EV-Peak",
    # Motors, ESCs, Flight Controllers & Stacks
    "BrotherHobby", "RCINPower", "Scorpion", "Xnova", "MAD Components", "MAD",
    "JHEMCU", "DarwinFPV", "Happymodel", "AxisFlying", "MicoAir", "Skystars",
    "Hakrc", "Flycolor", "NeutronRC", "Lumenier", "ImpulseRC", "Armattan",
    "RekonFPV", "Rekon", "NewBeeDrone", "Sub250", "DeepSpace", "AOS",
    "Five33", "Botgrinder", "Pyrodrone", "Speedix", "Spedix", "Racerstar",
    "Readytosky", "DYS", "ZTW", "APD", "Maytech", "Flipsky", "Dualsky", "Cobra",
    # Radios, Receivers, Telemetry & Video Links
    "TBS", "Team BlackSheep", "ImmersionRC", "Radiolink", "Flysky", "FrSky",
    "Jumper", "Futaba", "Spektrum", "HelloRadioSky", "NamimnoRC", "Bayck",
    "HDZero", "Divimath", "Orqa", "FatShark", "Fat Shark", "Eachine",
    "RunCam", "Hawkeye", "Insta360", "GoPro", "PandaRC", "AKK", "VTX",
    # Antennas
    "TrueRC", "Maple Wireless", "ORT", "Lollipop", "Pagoda", "Cherry",
    # Propellers
    "DALPROP", "Ethix", "APC", "Master Airscrew", "Azure Power", "Avan",
    "XOAR", "Eolo", "GF",
    # Agriculture, Industrial, Mapping, GPS & Sensors
    "EFT", "JIYI", "Hobbywing XRotor", "Ublox", "u-blox", "Beitian",
    "BZGNSS", "Benewake", "LightWare", "Slamtec", "RPLIDAR", "mRo",
    "Ark Electronics", "BotBlox", "Pixhawk", "ArduPilot",
    # Fixed-Wing, VTOL & Planes
    "HeeWing", "ATOMRC", "ZOHD", "Sonicmodell", "XUWING", "Finwing",
    "X-UAV", "XUAV", "Mapbird", "VolantexRC", "Volantex", "FMS", "Freewing",
    "OMPHOBBY", "WLtoys", "XK",
    # Servos, Connectors & Hardware
    "Amass", "TowerPro", "JX Servo", "KST", "GDW", "AGFRC", "Hitec",
    "Savox", "Corona", "Emax Servo", "DM09", "MG90S", "SG90", "MG995", "MG996R"
]

# Brand canonical normalization map
BRAND_ALIASES = {
    "t-motors": "T-Motor",
    "tmotor": "T-Motor",
    "t-hobby": "T-Hobby (T-Motor)",
    "caddxfpv": "Caddx",
    "mateksys": "Matek",
    "gaoneng": "GNB",
    "team blacksheep": "TBS",
    "fat shark": "FatShark",
    "rekon": "RekonFPV",
    "hex": "CubePilot",
    "proficnc": "CubePilot",
    "u-blox": "Ublox",
    "xuav": "X-UAV",
    "volantex": "VolantexRC",
    "mamba": "Diatone Mamba",
    "hq": "HQProp",
    "gf": "Gemfan",
}

# ----------------- STEP 1: EXPANDED INTENT UNDERSTANDING ENGINE (18 CATEGORIES) -----------------
CATEGORY_RULES = [
    ("Radio Transmitter / Controller", [
        r"\bpocket\b", r"\bboxer\b", r"\btx16s\b", r"\btx12\b", r"\bzorro\b",
        r"\bgx12\b", r"\bmt12\b", r"\bt12\b", r"\bt16\b", r"\bt20\b", r"\bt-lite\b",
        r"\bt-pro\b", r"\btransmitter\b", r"\bradio controller\b", r"\bfs-i6\b",
        r"\bfs-i6x\b", r"\bfs-i6s\b", r"\bfs-th9x\b", r"\bat9s\b", r"\bat10\b",
        r"\btaranis\b", r"\bhorus\b", r"\bhandset\b"
    ], [
        "receiver", "rx", "nano rx", "rp1", "rp2", "rp3", "rp4", "ep1", "ep2",
        "case", "strap", "neck strap", "stick end", "screen protector", "gimbal",
        "ag01", "battery", "pouch", "spring", "module", "ranger", "bandit", "cable",
        "dongle", "simulator", "trainer", "switch", "button", "shell", "stand"
    ]),
    ("FPV / RC Receiver (RX)", [
        r"\breceiver\b", r"\brx\b", r"\brp1\b", r"\brp2\b", r"\brp3\b", r"\brp4\b",
        r"\bep1\b", r"\bep2\b", r"\bnano rx\b", r"\bdiversity rx\b", r"\bsuperp\b",
        r"\bsuperd\b", r"\bia6b\b", r"\bfs-ia6b\b", r"\bfs-ia10b\b", r"\br8ef\b",
        r"\br12ds\b", r"\br9ds\b", r"\bxr1\b", r"\bxr2\b", r"\bxr3\b", r"\bxr4\b",
        r"\bcrossfire nano\b", r"\btracer nano\b"
    ], [
        "transmitter", "radio controller", "frame", "motor", "propeller", "goggles"
    ]),
    ("External TX Module (JR / Nano)", [
        r"\btx module\b", r"\branger\b", r"\bbandit\b", r"\bnomad\b",
        r"\bexternal module\b", r"\bmicro tx\b", r"\bnano tx\b", r"\bmultiprotocol module\b",
        r"\b4in1 module\b"
    ], [
        "frame", "motor", "propeller", "esc", "flight controller"
    ]),
    ("Flight Controller / FC Stack / Autopilot", [
        r"\bf405\b", r"\bf722\b", r"\bh743\b", r"\bf411\b", r"\bg473\b",
        r"\bflight controller\b", r"\bfc stack\b", r"\bstack\b", r"\bpixhawk\b",
        r"\bcube orange\b", r"\bcube blue\b", r"\bcube purple\b", r"\bcube black\b",
        r"\baio\b", r"\bk\+\+\b", r"\bjiyi\b", r"\bv5\+\b", r"\bv6x\b", r"\bn7\b",
        r"\bdurandal\b", r"\bkakute\b", r"\btaker\b", r"\bmamba\b", r"\bgoku\b",
        r"\bblitz\b", r"\bsuccex\b", r"\bpiko\b", r"\bkk2\b", r"\bapm\b"
    ], [
        "frame", "propeller", "motor", "goggles", "transmitter", "case",
        "usb cable", "dummy", "grommet", "damper", "mounting board"
    ]),
    ("Electronic Speed Controller (ESC)", [
        r"\besc\b", r"\b4-in-1\b", r"\b4in1\b", r"\bblheli\b", r"\bblheli_s\b",
        r"\bblheli_32\b", r"\bam32\b", r"\bsimonk\b", r"\bxrotor\b", r"\bplatinum\b",
        r"\bskywalker\b", r"\bvesc\b", r"\bfocal\b", r"\btekko32\b"
    ], [
        "frame", "propeller", "camera", "goggles", "transmitter", "capacitor"
    ]),
    ("Brushless Motor / Propulsion System", [
        r"\bmotor\b", r"\b\d{3,4}\s*kv\b", r"\bkv\b", r"\b0802\b", r"\b1002\b",
        r"\b1103\b", r"\b1104\b", r"\b1204\b", r"\b1303\b", r"\b1404\b", r"\b1408\b",
        r"\b1505\b", r"\b1507\b", r"\b1804\b", r"\b1806\b", r"\b2004\b", r"\b2005\b",
        r"\b2105\b", r"\b2203\b", r"\b2204\b", r"\b2205\b", r"\b2206\b", r"\b2207\b",
        r"\b2207\.5\b", r"\b2208\b", r"\b2212\b", r"\b2216\b", r"\b2306\b", r"\b2306\.5\b",
        r"\b2407\b", r"\b2408\b", r"\b2506\b", r"\b2507\b", r"\b2806\b", r"\b2806\.5\b",
        r"\b2807\b", r"\b2808\b", r"\b2810\b", r"\b2812\b", r"\b2814\b", r"\b3110\b",
        r"\b3115\b", r"\b3214\b", r"\b3508\b", r"\b4006\b", r"\b4008\b", r"\b4108\b",
        r"\b5008\b", r"\b6008\b", r"\b8120\b", r"\bx6 plus\b", r"\bx8\b", r"\bx9\b",
        r"\bxing\b", r"\bxing2\b", r"\bvelox\b", r"\bpacer\b", r"\bantigravity\b"
    ], [
        "frame", "propeller", "goggles", "transmitter", "spare bell", "replacement bell",
        "shaft", "bearing", "screw", "c-clip", "circlip", "washer", "motor mount", "wrench"
    ]),
    ("Multirotor / Agriculture Drone Frame", [
        r"\bframe\b", r"\bmark\s*4\b", r"\bmark\s*5\b", r"\bsource one\b",
        r"\bs500\b", r"\bs550\b", r"\bf450\b", r"\bf330\b", r"\btarot 650\b",
        r"\btarot 680\b", r"\bzd550\b", r"\bzd850\b", r"\be610p\b", r"\be616p\b",
        r"\be410p\b", r"\be416p\b", r"\bcinewhoop\b", r"\bcinelog\b", r"\bpavo\b",
        r"\bpavo20\b", r"\bpavo25\b", r"\bpavo35\b", r"\bapex\b", r"\bevoque\b",
        r"\bnazgul\b", r"\bmario\b", r"\bmaster\s*5\b", r"\bbeebee\b", r"\bvolador\b",
        r"\btanq\b", r"\bsiren\b", r"\bchameleon\b", r"\baura\b"
    ], [
        "spare arm", "replacement arm", "front arm", "rear arm", "top plate",
        "bottom plate", "middle plate", "side plate", "tpu", "screw", "standoff",
        "damper", "canopy", "duct guard"
    ]),
    ("Fixed-Wing / VTOL Aircraft Kit", [
        r"\bfixed wing\b", r"\bvtols?\b", r"\bxbird\b", r"\balbabird\b",
        r"\bt1 ranger\b", r"\bt2 cruza\b", r"\bpenguin\b", r"\bdolphin\b",
        r"\bswordfish\b", r"\bchupito\b", r"\btalon\b", r"\bskysurfer\b",
        r"\bdart\s*250g\b", r"\bdart\s*xl\b", r"\bdrift\b", r"\bar\s*wing\b",
        r"\bbixler\b", r"\bclouds\b", r"\branger\s*2000\b", r"\bphoenix\b"
    ], [
        "spare wing", "tail boom", "canopy", "hatch", "landing gear", "pushrod",
        "control horn", "clevis", "hinge", "camera seat"
    ]),
    ("Video
