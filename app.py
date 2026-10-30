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
    ("Video Transmitter (VTX) / Digital Air Unit", [
        r"\bvtx\b", r"\bvideo transmitter\b", r"\btx800\b", r"\btx1600\b",
        r"\btank\b", r"\bsolo\b", r"\bmax solo\b", r"\bblitz whoop\b",
        r"\breaper\b", r"\bzeus\b", r"\bo3 air unit\b", r"\bo4 air unit\b",
        r"\bavatar hd\b", r"\bmoonlight\b", r"\bfreestyle v2\b", r"\bwhoop vtx\b",
        r"\bunify pro\b", r"\bsixty9\b", r"\bsuccex force\b"
    ], [
        "frame", "motor", "propeller", "lens cap", "coaxial cable", "mipi cable",
        "heatsink", "mounting bracket"
    ]),
    ("FPV Camera / Gimbal / Thermal Payload", [
        r"\bcamera\b", r"\bcaddx\b", r"\bruncam\b", r"\bfoxeer\b", r"\bratel\b",
        r"\bant\b", r"\btoothless\b", r"\bt-rex\b", r"\bcat\s*3\b", r"\bcat\s*4\b",
        r"\bphoenix\b", r"\bnight eagle\b", r"\bstarlight\b", r"\bpolar\b",
        r"\bnbd beeeye\b", r"\bbeeeye\b", r"\ba8 mini\b", r"\bzr10\b", r"\bzr30\b",
        r"\bzt6\b", r"\bzt30\b", r"\bc13\b", r"\bc20\b", r"\bgimbal\b",
        r"\bthermal\b", r"\bthumb\b", r"\bhawkeye\b", r"\baction\s*2\b"
    ], [
        "lens cap", "replacement lens", "mount", "tpu", "cable", "housing",
        "nd filter", "back case", "bracket"
    ]),
    ("FPV Goggles / Video Monitor / VRX", [
        r"\bgoggles\b", r"\bev800d\b", r"\bev800dm\b", r"\bev100\b", r"\bsky04x\b",
        r"\bsky04o\b", r"\bcobra\s*x\b", r"\bcobra\s*sd\b", r"\bgoggles\s*2\b",
        r"\bgoggles\s*3\b", r"\bgoggles\s*n3\b", r"\bgoggles\s*x\b", r"\bdominator\b",
        r"\bscout\b", r"\brecon\b", r"\bfpv monitor\b", r"\bsteadyview\b",
        r"\brapidfire\b", r"\bwildfire\b", r"\bvrx\b"
    ], [
        "foam", "faceplate", "sponge", "strap", "head strap", "case", "diopter",
        "mat", "lens protector", "dvr board"
    ]),
    ("FPV & Telemetry Antennas", [
        r"\bantenna\b", r"\blollipop\b", r"\bpagoda\b", r"\bcherry\b",
        r"\bsingularity\b", r"\bx-air\b", r"\bpatch\b", r"\bhelical\b",
        r"\bmoxon\b", r"\bt-antenna\b", r"\bimmortal-t\b", r"\bdipole\b",
        r"\blhcp\b", r"\brhcp\b"
    ], [
        "antenna mount", "tpu", "tube", "cap", "pigtail adapter"
    ]),
    ("GPS, Compass & RTK Module", [
        r"\bgps\b", r"\bm10\b", r"\bm10q\b", r"\bm100\b", r"\bm8n\b", r"\bm9n\b",
        r"\bhere3\b", r"\bhere3\+\b", r"\bhere4\b", r"\bhere\s*pro\b", r"\bf9p\b",
        r"\brtk\b", r"\bneo-m8n\b", r"\bneo-3\b", r"\bbz-121\b", r"\bbz-181\b",
        r"\bbz-251\b", r"\bbe-180\b", r"\bbe-220\b", r"\bbe-250\b", r"\bbe-880\b"
    ], [
        "gps mount", "tpu", "folding mast", "pedestal", "stand", "holder", "case"
    ]),
    ("LiDAR, Optical Flow & Rangefinder Sensors", [
        r"\blidar\b", r"\boptical flow\b", r"\brangefinder\b", r"\btfmini\b",
        r"\btf-luna\b", r"\btf02\b", r"\btf03\b", r"\bmtf-01\b", r"\bmtf-02\b",
        r"\bpmw3901\b", r"\bpx4flow\b", r"\brplidar\b", r"\bsona\b", r"\bultrasonic\b",
        r"\bairspeed\b", r"\bpitot\b", r"\bradar\b"
    ], [
        "mount", "bracket", "case"
    ]),
    ("Propellers", [
        r"\bpropeller\b", r"\bprops?\b", r"\bgemfan\b", r"\bhqprop\b", r"\bdalprop\b",
        r"\bethix\b", r"\bhurri\b", r"\b51433\b", r"\b51466\b", r"\b51499\b",
        r"\b5043\b", r"\b5136\b", r"\b3016\b", r"\b3520\b", r"\b4024\b", r"\b6040\b",
        r"\b7040\b", r"\b7050\b", r"\b8040\b", r"\b9045\b", r"\b1045\b", r"\b1050\b",
        r"\b13x\b", r"\b15x\b", r"\b18x\b", r"\b22x\b", r"\b24x\b", r"\b30x\b"
    ], [
        "motor", "frame", "prop nut", "prop tool", "wrench", "balancer", "guard"
    ]),
    ("LiPo / Li-Ion Battery & Power Packs", [
        r"\blipo\b", r"\bli-ion\b", r"\bliion\b", r"\bbattery\b", r"\bmah\b",
        r"\b18650\b", r"\b21700\b", r"\bcnhl\b", r"\btattu\b", r"\bgens ace\b",
        r"\bovonic\b", r"\bgnb\b", r"\bherewin\b", r"\bp42a\b", r"\bp45b\b",
        r"\bp28a\b", r"\bvtc6\b", r"\b50s\b"
    ], [
        "battery strap", "kevlar strap", "velcro", "lipo bag", "safe bag",
        "charger", "buzzer", "voltage checker", "voltage alarm", "balance lead",
        "pad", "mat", "case"
    ]),
    ("Battery Chargers, Dischargers & PSU", [
        r"\bcharger\b", r"\bdischarger\b", r"\bm6\b", r"\bm6d\b", r"\bm6dac\b",
        r"\bm7\b", r"\bm8\b", r"\bm8p\b", r"\bq6\b", r"\bq4ac\b", r"\bd6 pro\b",
        r"\bb6\b", r"\bb6ac\b", r"\bk2\b", r"\bk4\b", r"\bp60\b", r"\bup1100\b",
        r"\bparallel board\b"
    ], [
        "screen protector", "bag", "carrying case"
    ]),
    ("RC Servos & Actuators", [
        r"\bservo\b", r"\bsg90\b", r"\bmg90s\b", r"\bmg995\b", r"\bmg996r\b",
        r"\bdm09\b", r"\bes08ma\b", r"\bes08md\b", r"\bes9251\b"
    ], [
        "servo horn", "servo arm", "extension wire", "tester", "bracket"
    ]),
]

# ----------------- EXPANDED ACCESSORY / SPARE PARTS POOL (120+ TERMS) -----------------
GENERAL_ACCESSORY_WORDS = {
    "case", "cases", "shell", "strap", "neck strap", "battery strap", "kevlar strap",
    "button", "buttons", "switch", "switches", "screw", "screws", "bolt", "bolts",
    "standoff", "standoffs", "spacer", "spacers", "nut", "nuts", "washer", "washers",
    "c-clip", "circlip", "e-clip", "retaining ring", "bearing", "bearings",
    "shaft", "replacement shaft", "spare bell", "replacement bell", "rotor bell",
    "spare", "spares", "replacement", "cable", "cables", "wire", "wires", "harness",
    "pigtail", "adapter", "connector", "plug", "mount", "mounts", "bracket", "brackets",
    "holder", "stand", "pedestal", "folding mast", "cap", "caps", "cover", "covers",
    "dust cover", "lens cap", "protector", "screen protector", "gimbal protector",
    "sticker", "stickers", "decal", "decals", "spring", "springs", "stick end",
    "stick ends", "thumb grippers", "pouch", "bag", "lipo bag", "safe bag", "backpack",
    "spare arm", "replacement arm", "front arm", "rear arm", "top plate", "bottom plate",
    "middle plate", "side plate", "bumper", "duct guard", "prop guard", "propeller guard",
    "pad", "pads", "landing pad", "landing skid", "landing gear", "o-ring", "grommet",
    "damper", "damping ball", "anti-vibration", "silicone", "sponge", "foam", "faceplate",
    "tpu", "3d printed", "3d print", "canopy", "hood", "heatsink", "cooling fan",
    "wrench", "tool", "driver", "screwdriver", "tweezers", "soldering mat", "flux",
    "heat shrink", "heatshrink", "tape", "velcro", "zip tie", "cable tie",
    "dummy", "practice board", "smoke stopper", "vifly", "buzzer", "finder",
    "trainer cable", "simulator dongle", "keychain", "lanyard", "t-shirt", "merch"
}

# ----------------- EXPANDED MODEL CONFLICT GROUPS -----------------
MODEL_CONFLICT_GROUPS = [
    {"pocket", "boxer", "tx16s", "tx12", "zorro", "mt12", "gx12", "t-lite", "t-pro", "t20"},
    {"f405", "f722", "h743", "f411", "g473"},
    {"v1", "v2", "v3", "v4", "v5"},
    {"mini", "wing", "aio", "bls", "pro", "max", "lite"},
    {"mark4", "mark5", "sourceone", "apex", "evoque", "cinelog25", "cinelog35", "pavo20", "pavo25", "pavo35", "s500", "s550", "f450", "tarot650"},
    {"rp1", "rp2", "rp3", "rp4", "ep1", "ep2", "xr1", "xr2", "xr3", "xr4", "superp", "superd"},
    {"m8n", "m9n", "m10", "here3", "here4"},
    {"o3", "o4", "avatar", "hdzero"},
    {"a8", "zr10", "zr30", "zt6", "zt30"},
    {"t10", "t12", "h12", "h16", "h30"},
    {"1404", "1507", "1804", "2004", "2205", "2207", "2212", "2306", "2506", "2806", "2807", "2812", "3115"},
]

# ----------------- EXPANDED TECHNICAL SYNONYMS POOL -----------------
SYNONYM_GROUPS = {
    "elrs": ["elrs", "expresslrs", "express lrs"],
    "expresslrs": ["elrs", "expresslrs", "express lrs"],
    "fc": ["fc", "flight controller"],
    "esc": ["esc", "speed controller", "4in1", "4-in-1"],
    "4in1": ["4in1", "4-in-1", "4 in 1"],
    "4-in-1": ["4in1", "4-in-1", "4 in 1"],
    "rx": ["rx", "receiver"],
    "receiver": ["rx", "receiver"],
    "tx": ["tx", "transmitter", "radio controller"],
    "vtx": ["vtx", "video transmitter"],
    "vrx": ["vrx", "video receiver"],
    "aio": ["aio", "all in one", "all-in-one"],
    "lipo": ["lipo", "li-po", "lithium polymer"],
    "liion": ["liion", "li-ion", "lithium ion"],
    "li-ion": ["liion", "li-ion", "lithium ion"],
    "crsf": ["crsf", "crossfire"],
    "crossfire": ["crsf", "crossfire"],
    "2.4g": ["2.4g", "2.4ghz", "2.4 ghz"],
    "2.4ghz": ["2.4g", "2.4ghz", "2.4 ghz"],
    "5.8g": ["5.8g", "5.8ghz", "5.8 ghz"],
    "5.8ghz": ["5.8g", "5.8ghz", "5.8 ghz"],
    "915": ["915", "915mhz", "915 mhz", "900mhz"],
    "915mhz": ["915", "915mhz", "915 mhz", "900mhz"],
    "868": ["868", "868mhz", "868 mhz"],
    "mark4": ["mark4", "mark 4", "mk4"],
    "mark5": ["mark5", "mark 5", "mk5"],
    "radiomaster": ["radiomaster", "radio master"],
    "speedybee": ["speedybee", "speedy bee"],
    "tmotor": ["tmotor", "t-motor", "t-hobby", "t motor"],
    "t-motor": ["tmotor", "t-motor", "t-hobby", "t motor"],
    "betafpv": ["betafpv", "beta fpv"],
    "flysky": ["flysky", "fly sky"],
    "frsky": ["frsky", "fr sky"],
    "hobbywing": ["hobbywing", "hobby wing"],
    "heewing": ["heewing", "hee wing"],
}

# ----------------- EXPANDED SPECIFICATION EXTRACTION REGEX POOL -----------------
SPEC_PATTERNS = [
    r"\b\d{4}\.\d\b|\b(?:0802|1002|1103|1104|1204|1303|1404|1408|1505|1507|1804|1806|2004|2005|2105|2204|2205|2206|2207|2208|2212|2216|2306|2407|2408|2506|2507|2806|2807|2808|2810|2812|2814|3110|3115|3214|3508|4006|4008|4108|5008|6008|8120)\b",
    r"\b\d{3,5}\s*KV\b",
    r"\b\d{1,3}\s*A(?:mp)?\b",
    r"\b(?:1[0-4]|[1-9])S(?:[1-6]P)?\b",
    r"\b\d{3,5}\s*mAh\b|\b\d{1,2}(?:\.\d+)?\s*Ah\b",
    r"\b\d{2,3}\s*C\b",
    r"\b2\.4\s*G(?:Hz)?\b|\b5\.8\s*G(?:Hz)?\b|\b1\.[23]\s*G(?:Hz)?\b",
    r"\b915\s*MHz\b|\b868\s*MHz\b|\b900\s*MHz\b|\b433\s*MHz\b",
    r"\bELRS\b|\bExpressLRS\b|\bCC2500\b|\b4-in-1\b|\b4in1\b|\bCrossfire\b|\bCRSF\b|\bSBUS\b|\bPWM\b|\bPPM\b|\bMavlink\b|\bDroneCAN\b|\bCAN\b",
    r"\bF405\b|\bF722\b|\bH743\b|\bF411\b|\bG473\b|\bSTM32\w*\b",
    r"\bBLHeli_S\b|\bBLHeli_32\b|\bBLHeli32\b|\bAM32\b|\bBluejay\b|\bSimonK\b|\bFOC\b",
    r"\bV[1-6](?:\.\d)?\b",
    r"\b\d+(?:\.\d+)?\s*(?:Inch|inch|\"|mm)\b",
    r"\b\d{2,4}\s*mW\b|\b\d+(?:\.\d+)?\s*W\b",
    r"\bM10\b|\bM10Q\b|\bM8N\b|\bM9N\b|\bF9P\b|\bRTK\b",
    r"\bO3\b|\bO4(?:\s*Pro)?\b|\bAvatar\b|\bWalksnail\b|\bHDZero\b|\bAnalog\b|\bStarlight\b|\b\d{3,4}\s*TVL\b|\b4K\b|\b1080[pP]\b",
    r"\b30\.5\s*x\s*30\.5\b|\b20\s*x\s*20\b|\b25\.5\s*x\s*25\.5\b|\b16\s*x\s*16\b",
    r"\bXT30\b|\bXT60\b|\bXT90\b|\bAS150\b|\bQS8\b|\bPH2\.0\b|\bBT2\.0\b|\bA30\b",
    r"\bSMA\b|\bRP-SMA\b|\bMMCX\b|\bU\.?FL\b|\bIPEX\b|\bLHCP\b|\bRHCP\b",
    r"\bHall\s*Gimbal\b|\bAG01\b|\bEdgeTX\b|\bOpenTX\b",
    r"\bCharcoal\b|\bTransparent\b|\bCrush\b|\bMode\s*[12]\b|\bM2\b"
]

# ----------------- INTENT ANALYSIS FUNCTION -----------------
def understand_user_query(raw_query: str, api_key: str = "") -> dict:
    q_clean = re.sub(r"[^a-zA-Z0-9\.\-]", " ", raw_query).strip()
    q_lower = q_clean.lower()

    # 1. Detect Primary Category & Category-Specific Exclusions
    detected_category = "General Drone Component"
    category_exclusions = set()
    for cat_name, patterns, exclusions in CATEGORY_RULES:
        if any(re.search(pat, q_lower) for pat in patterns):
            detected_category = cat_name
            category_exclusions = set(exclusions)
            break

    # 2. Extract Mandatory Core Tokens
    stop_words = {"for", "with", "and", "the", "in", "of", "to", "a", "an", "drone", "fpv", "rc", "buy", "india", "online"}
    raw_tokens = [t for t in q_lower.split() if len(t) >= 2 and t not in stop_words]
    if not raw_tokens:
        raw_tokens = q_lower.split()

    # 3. Identify Conflicting Sibling Models
    conflicting_tokens = set()
    q_nospace = q_lower.replace(" ", "")
    for group in MODEL_CONFLICT_GROUPS:
        matched_in_group = {
            t for t in group
            if re.search(rf"\b{re.escape(t)}\b", q_lower) or (len(t) >= 4 and t in q_nospace)
        }
        if matched_in_group:
            conflicting_tokens.update(group - matched_in_group)

    # 4. Build Active Exclusions Pool (unless user explicitly requested an accessory word)
    user_wants_accessory = any(re.search(rf"\b{re.escape(w)}\b", q_lower) for w in GENERAL_ACCESSORY_WORDS)
    active_exclusions = set()
    if not user_wants_accessory:
        active_exclusions.update(GENERAL_ACCESSORY_WORDS)
    for exc in category_exclusions:
        if exc not in q_lower:
            active_exclusions.add(exc)

    # Optional Gemini refinement if API key is provided
    if GEMINI_AVAILABLE and api_key:
        try:
            class QueryIntentSchema(BaseModel):
                category: str
                normalized_search_term: str
                must_have_keywords: list[str]
                exclude_keywords: list[str]

            client = genai.Client(api_key=api_key)
            res = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=f"""
                Analyze this drone hardware search query: "{raw_query}"
                Determine:
                1. category: Exact drone component category.
                2. normalized_search_term: Clean 2-4 word search string for vendor search bars.
                3. must_have_keywords: Lowercase words/model numbers that MUST be present in the product title.
                4. exclude_keywords: Lowercase words for accessories, spare parts, or other models that should be excluded.
                """,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=QueryIntentSchema,
                    temperature=0.0,
                ),
            )
            parsed = json.loads(res.text)
            if parsed.get("category"):
                detected_category = parsed["category"]
            if parsed.get("exclude_keywords"):
                for kw in parsed["exclude_keywords"]:
                    if kw.lower() not in q_lower:
                        active_exclusions.add(kw.lower())
        except Exception:
            pass

    return {
        "raw_query": raw_query.strip(),
        "search_term": q_clean,
        "category": detected_category,
        "must_tokens": raw_tokens,
        "conflicting_tokens": conflicting_tokens,
        "exclude_words": active_exclusions,
    }

# ----------------- STRICT PRODUCT RELEVANCE VERIFIER -----------------
def verify_product_matches_intent(title: str, intent: dict) -> tuple[bool, int]:
    if not title or len(title.strip()) < 5:
        return False, 0

    t_lower = title.lower().strip()
    t_compact = re.sub(r"[\s\-_]", "", t_lower)

    # 1. Reject website navigation links
    nav_blacklist = {
        "home", "shop", "cart", "view cart", "add to cart", "checkout", "my account",
        "login", "register", "wishlist", "compare", "track order", "contact us",
        "about us", "privacy policy", "terms and conditions", "read more", "search"
    }
    if t_lower in nav_blacklist:
        return False, 0

    # 2. Reject "For <Target>" / "Compatible with <Target>" accessory traps
    q_lower = intent["raw_query"].lower()
    if " for " not in q_lower:
        for must_tok in intent["must_tokens"]:
            if len(must_tok) >= 4:
                trap_pattern = rf"\b(?:for|compatible\s+with|suitable\s+for|fits|to\s+suit|replacement\s+for)\b[^,\|\(\)]*\b{re.escape(must_tok)}\b"
                if re.search(trap_pattern, t_lower):
                    return False, 0

    # 3. Require EVERY core token in `must_tokens` to match (with expanded synonym support)
    for tok in intent["must_tokens"]:
        synonyms = SYNONYM_GROUPS.get(tok, [tok])
        tok_matched = False
        for syn in synonyms:
            syn_compact = re.sub(r"[\s\-_]", "", syn)
            if syn in t_lower or syn_compact in t_compact:
                tok_matched = True
                break
        if not tok_matched:
            return False, 0

    # 4. Reject conflicting sibling models
    for conflict in intent["conflicting_tokens"]:
        if re.search(rf"\b{re.escape(conflict)}\b", t_lower):
            return False, 0

    # 5. Reject excluded accessory / cross-category words
    for exc in intent["exclude_words"]:
        if re.search(rf"\b{re.escape(exc)}\b", t_lower):
            return False, 0

    # 6. Compute relevance score
    score = 100
    if q_lower in t_lower:
        score += 50
    if t_lower.startswith(intent["must_tokens"][0]):
        score += 25
    score -= max(0, (len(t_lower) - 45) // 5)

    return True, score

# ----------------- METADATA EXTRACTORS -----------------
def detect_brand(title: str, default_brand: str = "") -> str:
    if default_brand and default_brand.lower() not in ["generic", "unknown", "n/a", ""]:
        alias_check = BRAND_ALIASES.get(default_brand.lower().strip())
        return alias_check if alias_check else default_brand

    t_lower = title.lower()
    for brand in KNOWN_BRANDS:
        b_low = brand.lower()
        # Match whole brand word or prefix
        if re.search(rf"\b{re.escape(b_low)}\b", t_lower) or b_low in t_lower:
            return BRAND_ALIASES.get(b_low, brand)

    first_word = re.sub(r"[^a-zA-Z0-9\-]", "", title.strip().split()[0]) if title.strip() else "Generic"
    return first_word if len(first_word) > 2 else "Generic"

def extract_specs_from_title(title: str, extra_desc: str = "") -> str:
    combined = f"{title} {extra_desc}"
    found = []
    for pat in SPEC_PATTERNS:
        for m in re.findall(pat, combined, re.I):
            clean_m = m.strip()
            if clean_m.upper() not in [x.upper() for x in found]:
                found.append(clean_m)
    if found:
        return " · ".join(found[:7])
    return "Standard Spec"

def parse_inr_price(text: str) -> float:
    if not text:
        return 0.0
    matches = re.findall(r"(?:₹|Rs\.?|INR)\s*([0-9,]+(?:\.[0-9]{1,2})?)", text, re.I)
    for m in matches:
        try:
            val = float(m.replace(",", ""))
            if 15 <= val <= 500000:
                return val
        except ValueError:
            pass
    return 0.0

# ----------------- VENDOR SCRAPING LAYER -----------------
def parse_markdown_listing(md_text: str, vendor: str, base_url: str, intent: dict) -> list[dict]:
    items = []
    lines = [l.strip() for l in md_text.splitlines() if l.strip()]

    for i, line in enumerate(lines):
        for m in re.finditer(r"\[([^\[\]]+)\]\((https?://[^\s\)]+)\)", line):
            raw_title = m.group(1).strip()
            url = m.group(2).strip()

            clean_title = re.sub(r"^(?:####+|###+|\*+|\-+)\s*", "", raw_title).strip()
            clean_title = re.sub(r"(?:Add to cart|Add to Wishlist|Add to Compare|Quick View).*$", "", clean_title, flags=re.I).strip()

            if any(skip_u in url.lower() for skip_u in [
                "facebook.com", "instagram.com", "twitter.com", "linkedin.com", "youtube.com",
                "/cart", "/checkout", "/my-account", "/login", "/wishlist", "add-to-cart=",
                "/category/", "/product-category/", "/tag/", "/blog/", "javascript:"
            ]):
                continue

            is_match, score = verify_product_matches_intent(clean_title, intent)
            if not is_match:
                continue

            start_idx = max(0, i - 1)
            end_idx = min(len(lines), i + 7)
            window_lines = []
            for j in range(start_idx, end_idx):
                if j > i and re.search(r"^#{2,5}\s*\[", lines[j]):
                    break
                window_lines.append(lines[j])
            window_blob = " \n ".join(window_lines)

            if re.search(r"out of stock|sold out|currently unavailable", window_blob, re.I):
                continue

            sku_match = re.search(r"SKU\s*[:#\-]?\s*([A-Za-z0-9_\-]+)", window_blob, re.I)
            sku = sku_match.group(1).strip() if sku_match else "N/A"
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

def parse_html_dom(html_text: str, vendor: str, base_url: str, intent: dict) -> list[dict]:
    items = []
    soup = BeautifulSoup(html_text, "html.parser")
    cards = soup.select(
        ".product, li.product, .product-grid-item, .type-product, "
        ".product-item, .product-card, .product-layout, .productListing-odd, .productListing-even"
    )

    for card in cards:
        card_text = card.get_text(" ", strip=True)
        if re.search(r"out of stock|sold out", card_text, re.I) or "out-of-stock" in " ".join(card.get("class", [])):
            continue

        title_el = card.select_one(
            ".woocommerce-loop-product__title, .product-title, .name, "
            "h2 a, h3 a, h4 a, h2, h3, h4, a.woocommerce-LoopProduct-link"
        )
        if not title_el:
            continue
        title = title_el.get_text(" ", strip=True)

        is_match, score = verify_product_matches_intent(title, intent)
        if not is_match:
            continue

        a_tag = title_el if title_el.name == "a" else card.select_one("a[href]")
        link = a_tag["href"] if a_tag and a_tag.has_attr("href") else base_url
        if link.startswith("/"):
            link = f"{base_url.rstrip('/')}{link}"

        sku_el = card.select_one(".sku, .product-sku")
        if sku_el:
            sku = sku_el.get_text(strip=True).replace("SKU:", "").strip()
        else:
            sku_m = re.search(r"SKU\s*[:#\-]?\s*([A-Za-z0-9_\-]+)", card_text, re.I)
            sku = sku_m.group(1) if sku_m else "N/A"

        ins_el = card.select_one("ins .amount, .price ins, .specialPrice, .sale-price")
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

async def fetch_via_jina(session: httpx.AsyncClient, jina_sem: asyncio.Semaphore, target_url: str) -> str:
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

async def fetch_ddg_vendor_fallback(session: httpx.AsyncClient, vendor: str, domain: str, intent: dict) -> list[dict]:
    items = []
    ddg_query = f"site:{domain} {intent['search_term']}"
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
                clean_title = re.split(r"\s+[\-\|–]\s+(?:Buy|Robu|Zbotic|Quadkart|Design Info|Indian Robo|Robokits|Xrobo|Tujo|Anubis|FPV)", raw_title, flags=re.I)[0].strip()

                href = a_el.get("href", "")
                if "uddg=" in href:
                    href = unquote(href.split("uddg=")[1].split("&")[0])

                if any(skip in href.lower() for skip in ["/category/", "/product-category/", "/tag/", "/blog/", "/brand/"]):
                    continue

                snippet = snip_el.get_text(" ", strip=True) if snip_el else ""
                combined_blob = f"{clean_title} {snippet}"

                if re.search(r"out of stock|sold out", combined_blob, re.I):
                    continue

                is_match, score = verify_product_matches_intent(clean_title, intent)
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
    intent: dict
) -> list[dict]:
    found_items = []
    query = intent["search_term"]

    # Layer 1: WooCommerce Store JSON API
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
                    is_match, score = verify_product_matches_intent(title, intent)
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

    # Layer 2: Direct HTML DOM
    search_url = f"{base_url}/?s={quote_plus(query)}&post_type=product"
    try:
        resp = await session.get(search_url, timeout=9.0)
        if resp.status_code == 200 and len(resp.text) > 500:
            found_items.extend(parse_html_dom(resp.text, vendor, base_url, intent))
    except Exception:
        pass

    if found_items:
        return found_items

    # Layer 3: Jina Reader Proxy
    md_text = await fetch_via_jina(session, jina_sem, search_url)
    if md_text:
        found_items.extend(parse_markdown_listing(md_text, vendor, base_url, intent))

    # Layer 4: Search Engine Site Discovery Fallback
    if not found_items and vendor in VENDOR_DOMAINS:
        found_items.extend(await fetch_ddg_vendor_fallback(session, vendor, VENDOR_DOMAINS[vendor], intent))

    return found_items

async def scrape_shopify_vendor(
    session: httpx.AsyncClient,
    jina_sem: asyncio.Semaphore,
    vendor: str,
    base_url: str,
    intent: dict
) -> list[dict]:
    found_items = []
    query = intent["search_term"]
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
                is_match, score = verify_product_matches_intent(title, intent)
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
            found_items.extend(parse_markdown_listing(md_text, vendor, base_url, intent))

    if not found_items and vendor in VENDOR_DOMAINS:
        found_items.extend(await fetch_ddg_vendor_fallback(session, vendor, VENDOR_DOMAINS[vendor], intent))

    return found_items

async def scrape_custom_or_notion_vendor(
    session: httpx.AsyncClient,
    jina_sem: asyncio.Semaphore,
    vendor: str,
    target_url: str,
    intent: dict
) -> list[dict]:
    found_items = []
    if vendor != "Danny’s Inventory List":
        try:
            resp = await session.get(target_url, timeout=9.0)
            if resp.status_code == 200 and len(resp.text) > 500:
                found_items.extend(parse_html_dom(resp.text, vendor, target_url, intent))
        except Exception:
            pass

    if not found_items:
        md_text = await fetch_via_jina(session, jina_sem, target_url)
        if md_text:
            found_items.extend(parse_markdown_listing(md_text, vendor, target_url, intent))

    if not found_items and vendor in VENDOR_DOMAINS:
        found_items.extend(await fetch_ddg_vendor_fallback(session, vendor, VENDOR_DOMAINS[vendor], intent))

    return found_items

async def run_all_scrapers(intent: dict, selected_vendors: list[str]) -> list[dict]:
    jina_sem = asyncio.Semaphore(3)
    all_items = []
    query = intent["search_term"]

    async with httpx.AsyncClient(headers=BROWSER_HEADERS, follow_redirects=True) as session:
        tasks = []
        for vendor, url in WOOCOMMERCE_VENDORS.items():
            if vendor in selected_vendors:
                tasks.append(scrape_woocommerce_vendor(session, jina_sem, vendor, url, intent))

        for vendor, url in SHOPIFY_VENDORS.items():
            if vendor in selected_vendors:
                tasks.append(scrape_shopify_vendor(session, jina_sem, vendor, url, intent))

        for vendor, search_prefix in CUSTOM_VENDORS.items():
            if vendor in selected_vendors:
                tasks.append(scrape_custom_or_notion_vendor(
                    session, jina_sem, vendor, f"{search_prefix}{quote_plus(query)}", intent
                ))

        if "Danny’s Inventory List" in selected_vendors:
            tasks.append(scrape_custom_or_notion_vendor(
                session, jina_sem, "Danny’s Inventory List", DANNY_NOTION_URL, intent
            ))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in results:
            if isinstance(res, list):
                all_items.extend(res)

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

# ----------------- ZERO-DEPENDENCY EXCEL (.XLSX) GENERATOR -----------------
def dataframe_to_xlsx_bytes(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    try:
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="BOQ")
        return buffer.getvalue()
    except ImportError:
        pass

    cols = list(df.columns)
    rows = [cols] + df.astype(str).values.tolist()

    sheet_rows_xml = []
    for r_idx, row_vals in enumerate(rows, start=1):
        cells_xml = []
        for c_idx, val in enumerate(row_vals):
            col_letter = chr(65 + c_idx)
            cell_ref = f"{col_letter}{r_idx}"
            if r_idx > 1 and c_idx in (0, 3):
                clean_num = re.sub(r"[^0-9\.]", "", str(val))
                if clean_num and clean_num.replace(".", "", 1).isdigit():
                    cells_xml.append(f'<c r="{cell_ref}"><v>{clean_num}</v></c>')
                    continue
            escaped_val = escape(str(val))
            cells_xml.append(f'<c r="{cell_ref}" t="inlineStr"><is><t>{escaped_val}</t></is></c>')
        sheet_rows_xml.append(f'<row r="{r_idx}">{"".join(cells_xml)}</row>')

    worksheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(sheet_rows_xml)}</sheetData>'
        '</worksheet>'
    )
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>'
    )
    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="BOQ" sheetId="1" r:id="rId1"/></sheets>'
        '</workbook>'
    )
    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '</Relationships>'
    )

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", rels_xml)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        zf.writestr("xl/worksheets/sheet1.xml", worksheet_xml)

    return buffer.getvalue()

# ----------------- SESSION STATE INITIALIZATION -----------------
if "boq_cart" not in st.session_state:
    st.session_state.boq_cart = []
if "search_results" not in st.session_state:
    st.session_state.search_results = []
if "last_intent" not in st.session_state:
    st.session_state.last_intent = None

# ----------------- SIDEBAR SETTINGS -----------------
with st.sidebar:
    st.markdown("### ⚙️ Settings")
    api_key = st.text_input(
        "Gemini API Key (Optional)",
        value=st.secrets.get("GEMINI_API_KEY", "") if "GEMINI_API_KEY" in st.secrets else "",
        type="password",
        help="Optional: Enhances intent classification using Gemini 2.0 Flash."
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
    hide_zero_price = st.checkbox("Hide items without listed price", value=False)

# ----------------- MINIMALIST HEADER -----------------
st.markdown("""
<div class="app-header">
    <div class="app-title">DroneProcurement — Smart Vendor Search & BOQ Builder</div>
    <p class="app-subtitle">Intent-verified component search across 13 Indian drone vendors (185+ indexed brands) with integrated Bill of Quantities (BOQ) cart</p>
</div>
""", unsafe_allow_html=True)

# ----------------- SINGLE SEARCH BAR -----------------
search_col, btn_col = st.columns([5, 1.2])
with search_col:
    query_input = st.text_input(
        "Search Drone Component",
        placeholder="Enter exact component or model name (e.g., Radiomaster Pocket, SpeedyBee F405 V4, 2207 1950KV Motor)...",
        label_visibility="collapsed"
    )
with btn_col:
    run_search = st.button("🔍 Search Vendors", type="primary", use_container_width=True)

# ----------------- STEP 1 + 2 EXECUTION -----------------
if run_search:
    if not query_input.strip():
        st.warning("Please enter a component name to search.")
    else:
        with st.spinner(f"Understanding query intent & scanning {len(selected_vendors)} vendors for '{query_input.strip()}'..."):
            intent_info = understand_user_query(query_input.strip(), api_key)
            matched_items = asyncio.run(run_all_scrapers(intent_info, selected_vendors))
            st.session_state.last_intent = intent_info
            st.session_state.search_results = matched_items

# ----------------- DISPLAY RECOGNIZED INTENT -----------------
if st.session_state.last_intent:
    intent = st.session_state.last_intent
    must_str = " + ".join([f'"{t}"' for t in intent["must_tokens"]])
    st.markdown(f"""
    <div class="intent-bar">
        <span>🧠 <b>Understood Intent:</b></span>
        <span>Category: <span class="intent-badge">{intent['category']}</span></span>
        <span>Required Keywords: <span class="intent-badge">{must_str}</span></span>
        <span style="color:#64748B;">Automatically filtered out spare parts, cases, and cross-category accessories</span>
    </div>
    """, unsafe_allow_html=True)

# ----------------- SEARCH RESULTS & ADD TO BOQ -----------------
results = st.session_state.search_results

if results:
    df_res = pd.DataFrame(results)
    if hide_zero_price:
        df_res = df_res[df_res["rate"] > 0]

    if not df_res.empty:
        df_res["_sort_rate"] = df_res["rate"].apply(lambda r: r if r and r > 0 else 9999999.0)
        df_res = df_res.sort_values(by=["_sort_rate", "relevance"], ascending=[True, False]).drop(columns=["_sort_rate"]).reset_index(drop=True)

        df_editor = pd.DataFrame({
            "Select": [False] * len(df_res),
            "Product Name": df_res["product_name"],
            "Specification": df_res["specification"],
            "Brand Name": df_res["brand_name"],
            "Vendor Name": df_res["vendor_name"],
            "SKU Name": df_res["sku_name"],
            "Rate (₹)": df_res["rate"],
            "Link": df_res["link"],
        })

        priced_only = df_res[df_res["rate"] > 0]
        lowest_str = f"₹{priced_only['rate'].min():,.2f}" if not priced_only.empty else "N/A"
        active_store_count = df_res["vendor_name"].nunique()

        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">1. Search Results (Sorted: Low to High Cost)</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-note">Tick the <b>Select</b> checkbox on any row below and click <b>Add Selected Item(s) to BOQ</b> to add it to your Bill of Quantities.</div>', unsafe_allow_html=True)

        st.markdown(f"""
        <div class="summary-strip">
            <div class="summary-pill">Matching Products: <b>{len(df_editor)}</b></div>
            <div class="summary-pill">Vendors with Stock: <b>{active_store_count}</b></div>
            <div class="summary-pill">Lowest Rate: <b>{lowest_str}</b></div>
        </div>
        """, unsafe_allow_html=True)

        edited_df = st.data_editor(
            df_editor,
            column_config={
                "Select": st.column_config.CheckboxColumn("Select", help="Tick to add this product to BOQ", default=False, width="small"),
                "Product Name": st.column_config.TextColumn("Product Name", width="large", disabled=True),
                "Specification": st.column_config.TextColumn("Specification", width="medium", disabled=True),
                "Brand Name": st.column_config.TextColumn("Brand Name", width="small", disabled=True),
                "Vendor Name": st.column_config.TextColumn("Vendor Name", width="small", disabled=True),
                "SKU Name": st.column_config.TextColumn("SKU Name", width="small", disabled=True),
                "Rate (₹)": st.column_config.NumberColumn("Rate (₹)", format="₹%.2f", disabled=True),
                "Link": st.column_config.LinkColumn("Link", display_text="Open Link ↗", disabled=True),
            },
            use_container_width=True,
            hide_index=True,
            key="search_results_editor"
        )

        act_col1, act_col2 = st.columns([2, 3])
        default_cat = st.session_state.last_intent["category"] if st.session_state.last_intent else "Drone Component"
        with act_col1:
            custom_cat = st.text_input(
                "Category for Selected Item(s)",
                value=default_cat,
                help="Auto-filled from your search intent. You can edit this before adding to BOQ."
            )
        with act_col2:
            st.write("")
            st.write("")
            if st.button("➕ Add Selected Item(s) to BOQ", type="primary"):
                selected_rows = edited_df[edited_df["Select"] == True]
                if selected_rows.empty:
                    st.warning("Please tick at least one item's 'Select' checkbox in the table above first.")
                else:
                    added_count = 0
                    for _, row in selected_rows.iterrows():
                        st.session_state.boq_cart.append({
                            "Category": custom_cat.strip() or default_cat,
                            "Item Name": row["Product Name"],
                            "Rate": float(row["Rate (₹)"]),
                            "Vendor": row["Vendor Name"],
                            "SKU": row["SKU Name"],
                            "Link": row["Link"],
                        })
                        added_count += 1
                    st.success(f"Added {added_count} item(s) to your BOQ table below! You can now search for your next component.")
                    st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)
elif st.session_state.last_intent is not None:
    st.info("No exact in-stock matches found for this specific item across the selected vendors. Try broadening the model name.")

# ----------------- PERSISTENT BOQ (BILL OF QUANTITIES) SECTION -----------------
st.markdown('<div class="section-card">', unsafe_allow_html=True)
st.markdown('<div class="section-title">2. Bill of Quantities (BOQ) Cart</div>', unsafe_allow_html=True)
st.markdown('<div class="section-note">Items added across all your searches appear here. You can edit categories directly, remove unwanted rows, or export the table to Excel (.xlsx).</div>', unsafe_allow_html=True)

if st.session_state.boq_cart:
    boq_df = pd.DataFrame(st.session_state.boq_cart)
    boq_df.insert(0, "Sr. No.", range(1, len(boq_df) + 1))
    boq_df["Remove"] = False

    total_boq_cost = boq_df["Rate"].sum()

    st.markdown(f"""
    <div class="summary-strip">
        <div class="summary-pill">Total BOQ Line Items: <b>{len(boq_df)}</b></div>
        <div class="summary-pill">Unique Vendors: <b>{boq_df['Vendor'].nunique()}</b></div>
        <div class="summary-pill">Estimated Total BOQ Value: <b>₹{total_boq_cost:,.2f}</b></div>
    </div>
    """, unsafe_allow_html=True)

    edited_boq = st.data_editor(
        boq_df,
        column_config={
            "Sr. No.": st.column_config.NumberColumn("Sr. No.", width="small", disabled=True),
            "Category": st.column_config.TextColumn("Category", width="medium"),
            "Item Name": st.column_config.TextColumn("Item Name", width="large"),
            "Rate": st.column_config.NumberColumn("Rate (₹)", format="₹%.2f"),
            "Vendor": st.column_config.TextColumn("Vendor", width="small", disabled=True),
            "SKU": st.column_config.TextColumn("SKU", width="small", disabled=True),
            "Link": st.column_config.LinkColumn("Link", display_text="Product Page ↗", disabled=True),
            "Remove": st.column_config.CheckboxColumn("Remove", help="Tick to remove row", default=False, width="small"),
        },
        use_container_width=True,
        hide_index=True,
        key="boq_table_editor"
    )

    # Sync inline edits back to session_state
    for idx in range(len(st.session_state.boq_cart)):
        st.session_state.boq_cart[idx]["Category"] = edited_boq.loc[idx, "Category"]
        st.session_state.boq_cart[idx]["Item Name"] = edited_boq.loc[idx, "Item Name"]
        st.session_state.boq_cart[idx]["Rate"] = float(edited_boq.loc[idx, "Rate"])

    export_df = edited_boq[["Sr. No.", "Category", "Item Name", "Rate", "Vendor", "SKU", "Link"]].copy()
    excel_bytes = dataframe_to_xlsx_bytes(export_df)

    b_col1, b_col2, b_col3 = st.columns([2, 1.5, 1.5])
    with b_col1:
        st.download_button(
            label="📥 Export BOQ to Excel (.xlsx)",
            data=excel_bytes,
            file_name="Drone_Parts_BOQ.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True
        )
    with b_col2:
        if st.button("🗑️ Remove Checked Rows", type="secondary", use_container_width=True):
            keep_indices = edited_boq[edited_boq["Remove"] == False].index.tolist()
            st.session_state.boq_cart = [st.session_state.boq_cart[i] for i in keep_indices]
            st.rerun()
    with b_col3:
        if st.button("🧹 Clear Entire BOQ", type="secondary", use_container_width=True):
            st.session_state.boq_cart = []
            st.rerun()
else:
    st.info("Your BOQ cart is currently empty. Search for a drone part above, tick the 'Select' checkbox on your desired vendor listing, and click 'Add Selected Item(s) to BOQ'.")

st.markdown('</div>', unsafe_allow_html=True)
