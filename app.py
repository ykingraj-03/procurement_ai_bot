import asyncio
import io
import json
import os
import re
import zipfile
from urllib.parse import quote_plus, unquote
from xml.sax.saxutils import escape
import httpx
from bs4 import BeautifulSoup
import pandas as pd
from PIL import Image
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
    page_title="The Drone Builder — AI-Assisted Vendor Search & BOQ Builder",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ----------------- MINIMALIST LIGHT PALETTE CSS -----------------
st.markdown("""
<style>
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
        padding-top: 1.5rem;
        padding-bottom: 3rem;
    }
    .app-title {
        font-size: 1.55rem;
        font-weight: 700;
        color: #0F172A;
        margin: 0 0 4px 0;
        letter-spacing: -0.02em;
    }
    .app-subtitle {
        font-size: 0.93rem;
        color: #475569;
        margin: 0;
    }
    .triage-card {
        background: #FEF3C7;
        border: 1px solid #F59E0B;
        border-radius: 10px;
        padding: 14px 18px;
        margin: 12px 0 20px 0;
        font-size: 0.88rem;
        color: #78350F;
    }
    .triage-title {
        font-weight: 700;
        font-size: 0.95rem;
        margin-bottom: 6px;
        display: flex;
        align-items: center;
        gap: 6px;
    }
    .ai-advisor-card {
        background: #FFFFFF;
        border: 1px solid #BFDBFE;
        border-left: 4px solid #2563EB;
        border-radius: 10px;
        padding: 14px 18px;
        margin: 12px 0 20px 0;
        font-size: 0.86rem;
        color: #1E293B;
        box-shadow: 0 1px 2px rgba(37, 99, 235, 0.04);
    }
    .ai-badge {
        background: #EFF6FF;
        border: 1px solid #BFDBFE;
        color: #1D4ED8;
        padding: 2px 9px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.78rem;
        margin-right: 6px;
        display: inline-block;
        margin-top: 4px;
    }
    .lock-badge {
        background: #DCFCE7;
        border: 1px solid #86EFAC;
        color: #166534;
        padding: 2px 9px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.78rem;
        margin-right: 6px;
        display: inline-block;
        margin-top: 4px;
    }
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
    "Robu": "robu.in", "Zbotic": "zbotic.in", "Tujo RC": "tujorc.com",
    "Quadkart": "quadkart.in", "Design Info": "designinfo.in", "Anubis Tech": "anubisrc.com",
    "FPV Guru": "fpvguru.in", "Hi Tech XYZ": "hitechxyz.in", "Xrobo": "xrobo.in",
    "Indian Robo Store": "indianrobostore.com", "Robokits": "robokits.co.in", "UAV Marketplace": "uavmarketplace.in",
}

DANNY_NOTION_URL = "https://danny8.notion.site/Danny-s-Inventory-List-214fd82319444160b57ffdf5ebb118bd"

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}

# ----------------- 185+ DRONE BRANDS -----------------
KNOWN_BRANDS = [
    "ZeroDrag", "Vimana", "Drakmatter", "Orange", "Bonka", "ProRange", "Garuda", "Quadkart", "Robokits", "Robu",
    "RadioMaster", "SpeedyBee", "T-Motor", "T-Hobby", "Hobbywing", "Holybro", "GEPRC", "Caddx", "CaddxFPV", "Walksnail",
    "BetaFPV", "Foxeer", "RushFPV", "Flywoo", "iFlight", "HGLRC", "Matek", "MatekSys", "Skyzone", "Emax", "Diatone",
    "Mamba", "Gemfan", "HQProp", "DJI", "SIYI", "Skydroid", "Herelink", "CubePilot", "HEX", "ProfiCNC", "CUAV", "Tarot",
    "SunnySky", "CNHL", "Ovonic", "Tattu", "Gens Ace", "GNB", "Gaoneng", "Herewin", "Auline", "Dogcom", "Zeee", "Turnigy",
    "BrotherHobby", "RCINPower", "Scorpion", "Xnova", "MAD Components", "MAD", "JHEMCU", "DarwinFPV", "Happymodel",
    "AxisFlying", "MicoAir", "Skystars", "Hakrc", "Flycolor", "NeutronRC", "Lumenier", "ImpulseRC", "Armattan", "RekonFPV",
    "NewBeeDrone", "Sub250", "DeepSpace", "AOS", "Five33", "Botgrinder", "Pyrodrone", "ZTW", "APD", "Maytech", "Flipsky",
    "Dualsky", "TBS", "Team BlackSheep", "ImmersionRC", "Radiolink", "Flysky", "FrSky", "Jumper", "Futaba", "Spektrum",
    "HDZero", "Divimath", "Orqa", "FatShark", "RunCam", "Hawkeye", "Insta360", "GoPro", "TrueRC", "Maple Wireless",
    "ORT", "DALPROP", "Ethix", "APC", "Master Airscrew", "XOAR", "Eolo", "EFT", "JIYI", "Ublox", "u-blox", "Beitian",
    "BZGNSS", "Benewake", "LightWare", "Slamtec", "RPLIDAR", "mRo", "Ark Electronics", "Pixhawk", "ArduPilot", "HeeWing",
    "ATOMRC", "ZOHD", "Sonicmodell", "X-UAV", "Mapbird", "VolantexRC", "FMS", "Freewing", "OMPHOBBY", "Amass", "JX Servo",
    "KST", "Surpass Hobby", "FlashHobby", "Flash Hobby", "SunFun"
]

BRAND_ALIASES = {
    "t-motors": "T-Motor", "tmotor": "T-Motor", "t-hobby": "T-Hobby (T-Motor)",
    "caddxfpv": "Caddx", "mateksys": "Matek", "gaoneng": "GNB", "team blacksheep": "TBS",
    "fat shark": "FatShark", "rekon": "RekonFPV", "hex": "CubePilot", "proficnc": "CubePilot",
    "flash hobby": "FlashHobby",
}

# ----------------- NON-DRONE / INDUSTRIAL / E-BIKE BLACKLIST -----------------
NON_DRONE_BLACKLIST = {
    "e-bike", "ebike", "my1016", "my1020", "scooter", "bicycle", "rickshaw", "wheelchair",
    "dc geared", "geared motor", "gear motor", "bo motor", "stepper motor", "nema17", "nema 17",
    "nema23", "nema 23", "775 motor", "rs775", "rs-775", "555 motor", "johnson motor",
    "water pump", "submersible", "wiper motor", "linear actuator", "cnc spindle", "lathe",
    "drill chuck", "vibration motor", "toy car", "robo race"
}

# ----------------- BROAD QUERY TRIAGE MAP -----------------
EXTREMELY_GENERAL_MAP = {
    "motor": {
        "patterns": [r"^(?:fpv\s+|drone\s+)?(?:brushless\s+)?motor[s]?$", r"^bldc(?:[\s\-]+motor[s]?)?$", r"^brushless\b$"],
        "message": "⚠️ Brushless motors range from 0.8g micro whoop motors to heavy-lift rotors. Select the drone class you are building:",
        "categories": {
            "Tiny Whoops (65-75mm)": {"search": "0802 motor", "subtext": "Stator 0702 / 0802 / 1002 (1S-2S Whoop)"},
            "2\" - 2.5\" Cinewhoop / Micro": {"search": "1404 motor", "subtext": "Stator 1404 / 1204 / 1303.5"},
            "3\" - 3.5\" Micro-Freestyle": {"search": "2004 motor", "subtext": "Stator 1507 / 1804 / 2004"},
            "5\" Freestyle & Racing": {"search": "5 inch fpv motors", "subtext": "Stator 2207 / 2306 (4S-6S)"},
            "7\" - 10\" Long Range": {"search": "7 inch long range motor", "subtext": "Stator 2806.5 / 2807 / 3115"},
            "Heavy-Lift / Cinelifter (3115)": {"search": "3115 900kv motor", "subtext": "Stator 3115 900KV (9-10 inch)"},
        }
    },
    "frame": {
        "patterns": [r"^(?:fpv\s+|drone\s+)?frame[s]?$", r"^chassis\b$"],
        "message": "⚠️ Drone frames are sized by propeller clearance. Select your target frame size:",
        "categories": {
            "Tiny Whoop (65-75mm)": {"search": "65mm whoop frame", "subtext": "Meteor65, Air65, Mobula"},
            "2.5\" CineWhoop Frame": {"search": "2.5 inch frame", "subtext": "Bee25, Pavo25, Cine25, CT25"},
            "3\" to 3.5\" Frame": {"search": "3.5 inch frame", "subtext": "Pavo35, CineLog35, Volador 3.5"},
            "5\" Standard Freestyle": {"search": "5 inch frame", "subtext": "Mark5, Mark4 5\", Source One V5"},
            "7\" - 10\" Long Range": {"search": "7 inch frame", "subtext": "Mark4 7\"/10\", Chimera7, LC75"},
            "Agriculture / Hex / Heavy": {"search": "S550 frame", "subtext": "S550, Tarot 650, EFT E410P/E616P"}
        }
    },
    "fc": {
        "patterns": [r"^(?:flight\s+)?controller[s]?$", r"^fc\b$", r"^autopilot\b$"],
        "message": "⚠️ Flight controllers vary by mounting pattern and firmware. Choose your application:",
        "categories": {
            "Tiny Whoop 1S-2S AIO": {"search": "1S AIO flight controller", "subtext": "25.5x25.5mm Whoop AIO boards"},
            "Cinewhoop / Toothpick AIO": {"search": "F405 AIO", "subtext": "20A-40A Toothpick / Cinewhoop AIO"},
            "5\"-10\" FPV Stack (F405/F722)": {"search": "5 inch stack", "subtext": "30.5x30.5mm F405/F722 FC + 4in1 ESC"},
            "Autonomous Pixhawk / Cube": {"search": "autopilot flight controller", "subtext": "Pixhawk, Cube Orange, Matek H743"},
        }
    },
    "propeller": {
        "patterns": [r"^(?:fpv\s+|drone\s+)?propeller[s]?$", r"^prop[s]?$", r"^blade[s]?$"],
        "message": "⚠️ Select the propeller diameter for your drone build:",
        "categories": {
            "2.5\" Cinewhoop Props": {"search": "2.5 inch prop", "subtext": "Gemfan D63, 2512, 2520"},
            "3\" - 3.5\" Props": {"search": "3.5 inch prop", "subtext": "3016, 3520, D90"},
            "5\" Freestyle & Racing Props": {"search": "5 inch prop", "subtext": "51433, 51466, 5043"},
            "7\" - 10\" Long Range Props": {"search": "7 inch prop", "subtext": "7040, 8040, 9045, 1050"},
        }
    },
    "battery": {
        "patterns": [r"^(?:fpv\s+|drone\s+)?battery$", r"^batteries$", r"^lipo$", r"^power\s*pack$"],
        "message": "⚠️ Select the battery voltage and capacity range:",
        "categories": {
            "Tiny Whoop 1S Battery": {"search": "1S 450mah lipo", "subtext": "BT2.0 / PH2.0 300-550mAh"},
            "Cinewhoop 4S (650-850mAh)": {"search": "4S 850mah lipo", "subtext": "XT30 4S 650mAh-850mAh"},
            "5\" FPV 6S (1100-1500mAh)": {"search": "5 inch lipo battery", "subtext": "XT60 4S/6S 1100-1550mAh"},
            "Long Range 6S Li-Ion / LiPo": {"search": "6S 3000mah", "subtext": "21700 Li-Ion / Large 6S Packs"},
        }
    }
}

# ----------------- AI DRONE BUILD COMPATIBILITY MATRIX -----------------
DRONE_SIZE_COMPATIBILITY = {
    "tinywhoop": {
        "size_patterns": [r"\b65\s*mm\b", r"\b75\s*mm\b", r"\btiny\s*whoop\b", r"\b1\.2\s*(?:inch|\")\b", r"\b1\.6\s*(?:inch|\")\b"],
        "motor": {
            "explanation": "65mm–75mm Tiny Whoop Brushless Motors -> Compatible Stators: 0702, 0802, 0803, 1002, 1102 (1S–2S)",
            "search_queries": ["0802 motor", "0702 motor", "1002 motor", "1102 motor", "0803 motor", "whoop motor"],
            "type_tokens": ["motor", "kv", "0702", "0802", "0803", "1002", "1102"],
            "spec_tokens": ["0702", "0802", "0803", "1002", "1102", "whoop", "1s", "65mm", "75mm"]
        },
        "frame": {
            "explanation": "65mm–75mm Tiny Whoop Frames -> Meteor65, Meteor75, Air65, Air75, Mobula6, Mobula7, Cockroach",
            "search_queries": ["65mm frame", "75mm frame", "meteor65", "air65", "air75", "cockroach frame"],
            "type_tokens": ["frame", "whoop", "kit", "meteor65", "meteor75", "air65", "air75", "cockroach"],
            "spec_tokens": ["65mm", "75mm", "meteor65", "meteor75", "air65", "air75", "mobula", "cockroach"]
        }
    },
    "2_inch": {
        "size_patterns": [r"\b2\s*(?:inch|\"|in|-inch)\b", r"\b20\s*(?:frame|cinewhoop)\b", r"\b95\s*mm\b"],
        "motor": {
            "explanation": "2-Inch Micro / Cinewhoop Motors -> Compatible Stators: 1003, 1103, 1104, 1204, 1303, 1303.5",
            "search_queries": ["1103 motor", "1204 motor", "1303.5 motor", "1303 motor", "1104 motor", "2 inch motor"],
            "type_tokens": ["motor", "kv", "1003", "1103", "1104", "1204", "1303"],
            "spec_tokens": ["1003", "1103", "1104", "1204", "1303", "1303.5", "c135", "2 inch", "2\"", "2inch"]
        },
        "frame": {
            "explanation": "2-Inch Cinewhoop & Micro Frames -> Pavo20, Cinelog20 (CL20), Cineon C20, Flylens 85",
            "search_queries": ["2 inch frame", "pavo20", "cinelog20", "cl20 frame", "cineon c20", "pavo 20"],
            "type_tokens": ["frame", "kit", "whoop", "pavo20", "cinelog20", "cl20", "c20"],
            "spec_tokens": ["2 inch", "2-inch", "2\"", "2''", "pavo20", "pavo 20", "cinelog20", "cl20", "c20", "85mm", "90mm", "95mm"]
        }
    },
    "2.5_inch": {
        "size_patterns": [r"\b2\.5\s*(?:inch|\"|''|in|-inch)?\b", r"\b25\s*(?:frame|cinewhoop|whoop)\b"],
        "motor": {
            "explanation": "2.5-Inch Cinewhoop / Toothpick Motors -> Compatible Stators: 1404, 1404.5, 1504, 1505, 1303.5, 1204 (3500KV–5000KV)",
            "search_queries": ["1404 motor", "1404.5 motor", "1504 motor", "1505 motor", "1303.5 motor", "2.5 inch motor"],
            "type_tokens": ["motor", "kv", "1404", "1504", "1505", "1303", "c145"],
            "spec_tokens": ["1404", "1404.5", "1504", "1505", "1303", "1303.5", "c145", "2.5 inch", "2.5inch", "2.5\""]
        },
        "frame": {
            "explanation": "2.5-Inch Frames & Cinewhoops -> SpeedyBee Bee25, GEPRC CT25 / Cinelog25, AOS Cine25, Axisflying Cineon C25V2, BetaFPV Pavo25, DeepSpace Stellar 25, iFlight Defender 25, Foxeer Foxwhoop 25",
            "search_queries": [
                "2.5 inch frame", "bee25", "cine25", "ct25",
                "c25v2", "stellar 25", "pavo25", "defender 25", "foxwoop 25"
            ],
            "type_tokens": [
                "frame", "kit", "cinewhoop", "bee25", "cine25", "ct25",
                "pavo25", "cinelog25", "c25", "c25v2", "stellar 25", "defender 25", "foxwoop"
            ],
            "spec_tokens": [
                "2.5 inch", "2.5-inch", "2.5\"", "2.5''", "2.5in", "2-5-frames", "2-5-inch", "25-inch",
                "bee25", "bee 25", "ct25", "ct 25", "cine25", "cine 25", "c25", "c25v2",
                "pavo25", "pavo 25", "cinelog25", "cinelog 25", "cl25", "stellar 25", "stellar25",
                "cineape 25", "defender 25", "foxwoop 25", "foxwhoop 25", "nanohawk", "babyape",
                "tinytrainer", "110mm", "112mm", "113mm", "115mm", "120mm", "125mm"
            ]
        },
        "prop": {
            "explanation": "2.5-Inch Propellers -> Gemfan D63, 2512, 2520, 2525, HQProp 2.5\"",
            "search_queries": ["2.5 inch prop", "2512 prop", "2520 prop", "d63 prop", "63mm prop"],
            "type_tokens": ["prop", "propeller", "gemfan", "hqprop", "duct"],
            "spec_tokens": ["2.5", "2512", "2520", "2525", "d63", "63mm", "65mm"]
        }
    },
    "3_to_3.5_inch": {
        "size_patterns": [r"\b3\.5\s*(?:inch|\"|''|in|-inch)?\b", r"\b3\s*(?:inch|\"|''|in|-inch)\b", r"\b35\s*(?:frame|cinewhoop)\b"],
        "motor": {
            "explanation": "3-Inch to 3.5-Inch Motors -> Compatible Stators: 1507, 1604, 1804, 2004, 2006, 1408 (2400KV–3800KV)",
            "search_queries": ["1804 motor", "2004 motor", "1507 motor", "1604 motor", "2006 motor", "3.5 inch motor"],
            "type_tokens": ["motor", "kv", "1507", "1604", "1804", "2004", "2006", "1408"],
            "spec_tokens": ["1507", "1604", "1804", "2004", "2006", "1408", "c204", "c206", "c157", "3 inch", "3.5 inch", "3\"", "3.5\""]
        },
        "frame": {
            "explanation": "3-Inch to 3.5-Inch Frames -> SpeedyBee Master3X, GEPRC CL35 / CT30, AOS Cine35, BetaFPV Pavo35, Axisflying Cineon C35 / C30, Foxeer Aura 3.5 / Caesar 3.5, HGLRC Veyron35, Volador 3.5, Holybro Kopis 3",
            "search_queries": [
                "3.5 inch frame", "3 inch frame", "master3x", "cl35",
                "cine35", "pavo35", "cineon c35", "ct30", "volador 3.5"
            ],
            "type_tokens": [
                "frame", "kit", "master3x", "cine35", "pavo35", "cinelog35",
                "cl35", "ct30", "crux35", "volador", "veyron35", "aura", "caesar", "kopis"
            ],
            "spec_tokens": [
                "3.5 inch", "3.5-inch", "3.5\"", "3.5''", "3.5inch", "3 inch", "3\"", "3''", "3-3.6",
                "master3x", "cine35", "pavo35", "cinelog35", "cinelog 35", "cl35", "ct30",
                "cineon c35", "cineon c30", "veyron35", "crux35", "siren f35", "aos 3.5",
                "volador 3.5", "volador ii vd3.5", "aura 3.5", "caesar 3", "kopis", "ih3",
                "140mm", "145mm", "150mm", "155mm", "160mm"
            ]
        },
        "prop": {
            "explanation": "3-Inch to 3.5-Inch Propellers -> 3016, 3020, 3520, 3525, D90",
            "search_queries": ["3.5 inch prop", "3520 prop", "3016 prop", "d90 prop", "3 inch prop"],
            "type_tokens": ["prop", "propeller", "gemfan", "hqprop"],
            "spec_tokens": ["3.5", "3 inch", "3016", "3020", "3520", "3525", "d90"]
        }
    },
    "5_inch": {
        "size_patterns": [r"\b5\s*(?:inch|\"|''|in|-inch)\b", r"\b5\"\b", r"\b210\s*mm\b", r"\b220\s*mm\b", r"\b225\s*mm\b"],
        "motor": {
            "explanation": "5-Inch FPV Freestyle & Racing Motors -> Standard Stators: 2207, 2306, 2306.5, 2205, 2206, 2208, 2407 (1700KV–2750KV 4S/6S)",
            "search_queries": [
                "2207 motor", "2306 motor", "2306.5 motor", "2205 motor",
                "5 inch motor", "eco ii 2207", "xing 2207", "velox 2207"
            ],
            "type_tokens": ["motor", "kv", "2207", "2306", "2205", "2206", "2208", "2407", "velox", "xing", "pacer", "supernova", "eco"],
            "spec_tokens": [
                "2207", "2207.5", "2306", "2306.5", "2205", "2206", "2208", "2407",
                "5 inch", "5-inch", "5\"", "5''", "5-6 inch", "master5"
            ]
        },
        "frame": {
            "explanation": "5-Inch FPV Freestyle & Racing Frames -> GEPRC Mark5 (MK5), Mark4 5\", TBS Source One V5, SpeedyBee Mario 5 / Master 5, iFlight Nazgul5 / Evoque F5, Foxeer Aura 5, HGLRC Sector D5, ImpulseRC Apex 5, Flywoo Volador 5",
            "search_queries": [
                "5 inch frame", "mark5 frame", "mk5 frame", "mario 5 frame",
                "mark4 5 inch", "source one v5", "nazgul5", "evoque f5"
            ],
            "type_tokens": [
                "frame", "kit", "mark4", "mark5", "mk5", "source one", "source two",
                "apex", "volador", "mario 5", "master 5", "nazgul", "evoque", "aura", "sector", "manta", "switchback"
            ],
            "spec_tokens": [
                "5 inch", "5-inch", "5\"", "5''", "5inch", "mark5", "mark 5", "mk5", "mk5x", "mk5d",
                "mark4 5", "source one", "source two", "apex 5", "apex evo", "volador 5", "volador ii vd5",
                "mario 5", "master 5", "nazgul5", "evoque f5", "f5x", "f5d", "tanq 5", "aura 5",
                "sector d5", "manta5", "manta 5", "goku gx5", "switchback", "210mm", "215mm", "220mm", "225mm", "230mm"
            ]
        },
        "prop": {
            "explanation": "5-Inch FPV Propellers -> 51433, 51466, 5043, 51499, 5136, 5x4.3x3",
            "search_queries": ["5 inch prop", "51433 prop", "51466 prop", "5043 prop", "hqprop 5"],
            "type_tokens": ["prop", "propeller", "gemfan", "hqprop", "dalprop", "ethix"],
            "spec_tokens": ["5 inch", "5\"", "51433", "51466", "5043", "51499", "5136", "5045", "5x"]
        },
        "stack": {
            "explanation": "5-Inch FPV Flight Controller & 4-in-1 ESC Stacks -> 30.5x30.5mm F405 / F722 with 45A–65A 4-in-1 ESC",
            "search_queries": ["f405 stack", "f722 stack", "55a stack", "50a stack", "60a stack"],
            "type_tokens": ["stack", "f405", "f722", "flight controller", "esc"],
            "spec_tokens": ["f405", "f722", "45a", "50a", "55a", "60a", "65a", "30x30", "30.5"]
        },
        "battery": {
            "explanation": "5-Inch FPV LiPo Batteries -> 4S / 6S 1100mAh–1550mAh High-Discharge (100C–150C) XT60 Packs",
            "search_queries": ["1300mah 6s", "1500mah 4s", "1500mah 6s", "1100mah 6s", "1400mah 6s"],
            "type_tokens": ["lipo", "battery", "mah", "cnhl", "tattu", "ovonic", "gnb", "bonka", "orange"],
            "spec_tokens": ["1100mah", "1200mah", "1300mah", "1350mah", "1400mah", "1500mah", "1550mah"]
        }
    },
    "7_to_10_inch": {
        "size_patterns": [r"\b(?:7|8|9|10)\s*(?:inch|\"|''|in|-inch)\b", r"\blong\s*range\s*(?:motor|frame)\b"],
        "motor": {
            "explanation": "7-Inch to 10-Inch Long-Range & Heavy-Lift Motors -> Compatible Stators: 2806.5, 2807, 2808, 2810, 2812, 3110, 3115 (900KV–1500KV)",
            "search_queries": ["2807 motor", "2806.5 motor", "3115 motor", "2812 motor", "2808 motor", "em2807"],
            "type_tokens": ["motor", "kv", "2806", "2807", "2808", "2810", "2812", "3110", "3115"],
            "spec_tokens": ["2806", "2806.5", "2807", "2808", "2810", "2812", "3110", "3115", "7 inch", "8 inch", "10 inch"]
        },
        "frame": {
            "explanation": "7-Inch to 10-Inch Long-Range Frames -> Mark4 7\" / 8\" / 10\", iFlight Chimera7, GEPRC LC75, Foxeer Mega 7, Rekon7, Moz7",
            "search_queries": ["7 inch frame", "mark4 7", "10 inch frame", "chimera7", "lc75 frame", "mega 7 frame"],
            "type_tokens": ["frame", "kit", "mark4", "chimera", "rekon", "crocodile", "moz7", "lc75", "mega 7"],
            "spec_tokens": [
                "7 inch", "7-inch", "7\"", "7inch", "8 inch", "8\"", "9 inch", "10 inch", "10\"",
                "mark4 7", "mark4-7", "mark4 10", "chimera7", "lc75", "mega 7", "rekon7", "moz7", "295mm", "315mm", "420mm"
            ]
        },
        "prop": {
            "explanation": "7-Inch to 10-Inch Long-Range Propellers -> 7040, 7037, 7050, 8040, 9045, 1045, 1050",
            "search_queries": ["7 inch prop", "7040 prop", "1050 prop", "8040 prop", "1045 prop"],
            "type_tokens": ["prop", "propeller", "gemfan", "hqprop", "master airscrew", "apc"],
            "spec_tokens": ["7 inch", "7\"", "7040", "7037", "7050", "8040", "9045", "1045", "1050", "10x"]
        }
    }
}

# ----------------- CATEGORY & EXCLUSION POOLS -----------------
CATEGORY_RULES = [
    ("Radio Transmitter / Controller", [
        r"\bpocket\b", r"\bboxer\b", r"\btx16s\b", r"\btx12\b", r"\bzorro\b",
        r"\bgx12\b", r"\bmt12\b", r"\bt12\b", r"\bt16\b", r"\bt20\b", r"\bt-lite\b",
        r"\bt-pro\b", r"\btransmitter\b", r"\bradio controller\b", r"\bfs-i6\b",
        r"\bfs-i6x\b", r"\bfs-i6s\b", r"\bfs-th9x\b", r"\bat9s\b", r"\bat10\b"
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
        r"\bxr1\b", r"\bxr2\b", r"\bxr3\b", r"\bxr4\b", r"\bcrossfire nano\b"
    ], [
        "transmitter", "radio controller", "frame", "motor", "propeller", "goggles"
    ]),
    ("Flight Controller / FC Stack / Autopilot", [
        r"\bf405\b", r"\bf722\b", r"\bh743\b", r"\bf411\b", r"\bg473\b",
        r"\bflight controller\b", r"\bfc stack\b", r"\bstack\b", r"\bpixhawk\b",
        r"\bcube orange\b", r"\baio\b", r"\bk\+\+\b", r"\bjiyi\b", r"\bv5\+\b",
        r"\bv6x\b", r"\bn7\b", r"\bkakute\b", r"\btaker\b", r"\bmamba\b", r"\bblitz\b"
    ], [
        "frame", "propeller", "motor", "goggles", "transmitter", "case",
        "usb cable", "dummy", "grommet", "damper", "mounting board"
    ]),
    ("Electronic Speed Controller (ESC)", [
        r"\besc\b", r"\b4-in-1\b", r"\b4in1\b", r"\bblheli\b", r"\bam32\b",
        r"\bxrotor\b", r"\bplatinum\b", r"\bskywalker\b", r"\btekko32\b"
    ], [
        "frame", "propeller", "camera", "goggles", "transmitter", "capacitor"
    ]),
    ("Brushless Motor", [
        r"\bmotors?\b", r"\b\d{3,4}\s*kv\b", r"\bkv\b", r"\b0802\b", r"\b1002\b",
        r"\b1103\b", r"\b1104\b", r"\b1204\b", r"\b1303\b", r"\b1404\b", r"\b1507\b",
        r"\b1804\b", r"\b2004\b", r"\b2204\b", r"\b2205\b", r"\b2206\b", r"\b2207\b",
        r"\b2208\b", r"\b2212\b", r"\b2306\b", r"\b2407\b", r"\b2806\b", r"\b2807\b",
        r"\b2812\b", r"\b3110\b", r"\b3115\b", r"\b3508\b", r"\bxing\b", r"\bxing2\b",
        r"\bvelox\b", r"\bpacer\b"
    ], [
        "frame", "propeller", "goggles", "transmitter", "spare bell", "replacement bell",
        "shaft", "bearing", "screw", "c-clip", "circlip", "washer", "motor mount", "wrench"
    ]),
    ("Drone Frame", [
        r"\bframes?\b", r"\bmark\s*4\b", r"\bmark\s*5\b", r"\bsource one\b",
        r"\bs500\b", r"\bs550\b", r"\bf450\b", r"\btarot 650\b", r"\bcinewhoop\b",
        r"\bcinelog\b", r"\bpavo\b", r"\bpavo20\b", r"\bpavo25\b", r"\bpavo35\b",
        r"\bcine25\b", r"\bcine35\b", r"\bbee25\b", r"\bct25\b", r"\bapex\b", r"\bevoque\b", r"\bvolador\b"
    ], [
        "spare arm", "replacement arm", "front arm", "rear arm", "arms set", "arm set",
        "top plate", "bottom plate", "middle plate", "side plate", "bumper", "duct guard",
        "prop guard", "propeller guard", "landing pad", "landing skid", "landing gear",
        "o-ring", "grommet", "damper", "damping ball", "anti-vibration", "sponge",
        "faceplate", "tpu", "3d printed", "3d print", "canopy", "hood", "heatsink",
        "cooling fan", "wrench", "screwdriver", "tweezers", "soldering mat",
        "dummy", "practice board", "smoke stopper", "trainer cable", "simulator dongle"
    ]),
    ("Video Transmitter (VTX) / Air Unit", [
        r"\bvtx\b", r"\bvideo transmitter\b", r"\btx800\b", r"\btx1600\b",
        r"\btank\b", r"\bsolo\b", r"\breaper\b", r"\bo3 air unit\b", r"\bo4 air unit\b",
        r"\bavatar hd\b", r"\bmoonlight\b"
    ], [
        "frame", "motor", "propeller", "lens cap", "coaxial cable", "mipi cable", "heatsink"
    ]),
    ("FPV Camera / Gimbal", [
        r"\bcameras?\b", r"\bcaddx\b", r"\bruncam\b", r"\bfoxeer\b", r"\bratel\b",
        r"\bant\b", r"\btoothless\b", r"\ba8 mini\b", r"\bzr10\b", r"\bzr30\b",
        r"\bc13\b", r"\bgimbal\b", r"\bthermal\b"
    ], [
        "lens cap", "replacement lens", "mount", "tpu", "cable", "housing", "nd filter"
    ]),
    ("FPV Goggles / Video Monitor", [
        r"\bgoggles\b", r"\bev800d\b", r"\bsky04x\b", r"\bcobra\s*x\b",
        r"\bcobra\s*sd\b", r"\bdominator\b", r"\bfpv monitor\b"
    ], [
        "foam", "faceplate", "sponge", "strap", "head strap", "case", "diopter", "mat"
    ]),
    ("GPS, Compass & RTK Module", [
        r"\bgps\b", r"\bm10\b", r"\bm10q\b", r"\bm8n\b", r"\bm9n\b",
        r"\bhere3\b", r"\bhere4\b", r"\bf9p\b", r"\brtk\b"
    ], [
        "gps mount", "tpu", "folding mast", "pedestal", "stand", "holder", "case"
    ]),
    ("Propellers", [
        r"\bpropellers?\b", r"\bprops?\b", r"\bgemfan\b", r"\bhqprop\b",
        r"\bdalprop\b", r"\bethix\b", r"\b51433\b", r"\b51466\b"
    ], [
        "motor", "frame", "prop nut", "prop tool", "wrench", "balancer", "guard"
    ]),
    ("LiPo / Li-Ion Battery", [
        r"\blipo\b", r"\bli-ion\b", r"\bliion\b", r"\bbattery\b", r"\bbatteries\b",
        r"\bmah\b", r"\bcnhl\b", r"\btattu\b", r"\bgens ace\b", r"\bovonic\b", r"\bgnb\b"
    ], [
        "battery strap", "kevlar strap", "velcro", "lipo bag", "safe bag",
        "charger", "buzzer", "voltage checker", "balance lead", "pad", "mat"
    ]),
]

GENERAL_ACCESSORY_WORDS = {
    "case", "cases", "shell", "neck strap", "battery strap", "kevlar strap",
    "button", "buttons", "switch", "switches", "screw", "screws", "bolt", "bolts",
    "standoff", "standoffs", "spacer", "spacers", "nut", "nuts", "washer", "washers",
    "c-clip", "circlip", "e-clip", "retaining ring", "bearing", "bearings",
    "replacement shaft", "spare bell", "replacement bell", "rotor bell",
    "spare", "spares", "replacement", "cable", "cables", "wire", "wires", "harness",
    "pigtail", "adapter", "connector", "plug", "mount", "mounts", "bracket", "brackets",
    "holder", "stand", "pedestal", "folding mast", "cap", "caps", "cover", "covers",
    "dust cover", "lens cap", "protector", "screen protector", "gimbal protector",
    "sticker", "stickers", "decal", "decals", "spring", "springs", "stick end",
    "stick ends", "thumb grippers", "pouch", "lipo bag", "safe bag", "backpack",
    "spare arm", "replacement arm", "front arm", "rear arm", "arms set", "arm set",
    "top plate", "bottom plate", "middle plate", "side plate", "bumper", "duct guard",
    "prop guard", "propeller guard", "landing pad", "landing skid", "landing gear",
    "o-ring", "grommet", "damper", "damping ball", "anti-vibration", "sponge",
    "faceplate", "tpu", "3d printed", "3d print", "canopy", "hood", "heatsink",
    "cooling fan", "wrench", "screwdriver", "tweezers", "soldering mat",
    "dummy", "practice board", "smoke stopper", "trainer cable", "simulator dongle"
}

ALL_KNOWN_STATORS = {
    "0702", "0802", "0803", "1002", "1003", "1102", "1103", "1104", "1105", "1106",
    "1202", "1204", "1303", "1306", "1404", "1407", "1408", "1504", "1505", "1506",
    "1507", "1604", "1606", "1804", "1806", "2004", "2005", "2006", "2104", "2105",
    "2203", "2204", "2205", "2206", "2207", "2208", "2212", "2216", "2305", "2306",
    "2307", "2308", "2405", "2407", "2408", "2506", "2507", "2508", "2806", "2807",
    "2808", "2810", "2812", "2814", "2820", "3110", "3112", "3115", "3214", "3508",
    "3510", "3515", "3520", "4004", "4006", "4008", "4108", "4114", "4215", "5008",
    "5010", "5208", "6008", "6215", "8120", "8318", "10010"
}

MODEL_CONFLICT_GROUPS = [
    {"pocket", "boxer", "tx16s", "tx12", "zorro", "mt12", "gx12", "t-lite", "t-pro", "t20"},
    {"f405", "f722", "h743", "f411", "g473"},
    {"v1", "v2", "v3", "v4", "v5"},
    {"rp1", "rp2", "rp3", "rp4", "ep1", "ep2", "xr1", "xr2", "xr3", "xr4"},
    {"m8n", "m9n", "m10", "here3", "here4"},
    {"o3", "o4", "avatar", "hdzero"},
    ALL_KNOWN_STATORS,
]

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
    "aio": ["aio", "all in one", "all-in-one"],
    "lipo": ["lipo", "li-po", "lithium polymer"],
    "liion": ["liion", "li-ion", "lithium ion"],
    "crsf": ["crsf", "crossfire"],
    "mark4": ["mark4", "mark 4", "mk4"],
    "mark5": ["mark5", "mark 5", "mk5"],
    "radiomaster": ["radiomaster", "radio master"],
    "speedybee": ["speedybee", "speedy bee"],
    "tmotor": ["tmotor", "t-motor", "t-hobby", "t motor"],
    "t-motor": ["tmotor", "t-motor", "t-hobby", "t motor"],
    "betafpv": ["betafpv", "beta fpv"],
    "motor": ["motor", "motors", "bldc", "kv"],
    "motors": ["motor", "motors", "bldc", "kv"],
    "frame": ["frame", "frames", "kit", "cinewhoop"],
    "frames": ["frame", "frames", "kit", "cinewhoop"],
    "prop": ["prop", "props", "propeller", "propellers"],
    "props": ["prop", "props", "propeller", "propellers"],
    "propeller": ["prop", "props", "propeller", "propellers"],
}

SPEC_PATTERNS = [
    r"\b\d{4}\.\d\b|\b(?:0702|0802|0803|1002|1102|1103|1104|1204|1303|1404|1408|1504|1505|1507|1604|1804|1806|2004|2006|2105|2204|2205|2206|2207|2208|2212|2216|2306|2407|2408|2506|2507|2806|2807|2808|2810|2812|2814|3110|3115|3214|3508|4006|4008|4108|5008|6008|8120)\b",
    r"\b\d{3,5}\s*KV\b",
    r"\b\d{1,3}\s*A(?:mp)?\b",
    r"\b(?:1[0-4]|[1-9])S(?:[1-6]P)?\b",
    r"\b\d{3,5}\s*mAh\b|\b\d{1,2}(?:\.\d+)?\s*Ah\b",
    r"\b\d{2,3}\s*C\b",
    r"\b2\.4\s*G(?:Hz)?\b|\b5\.8\s*G(?:Hz)?\b|\b1\.[23]\s*G(?:Hz)?\b",
    r"\b915\s*MHz\b|\b868\s*MHz\b|\b900\s*MHz\b|\b433\s*MHz\b",
    r"\bELRS\b|\bExpressLRS\b|\bCC2500\b|\b4-in-1\b|\b4in1\b|\bCrossfire\b|\bCRSF\b|\bSBUS\b|\bMavlink\b|\bDroneCAN\b",
    r"\bF405\b|\bF722\b|\bH743\b|\bF411\b|\bG473\b",
    r"\bBLHeli_S\b|\bBLHeli_32\b|\bBLHeli32\b|\bAM32\b|\bBluejay\b",
    r"\bV[1-6](?:\.\d)?\b",
    r"\b\d+(?:\.\d+)?\s*(?:Inch|inch|\"|mm)\b",
    r"\b\d{2,4}\s*mW\b|\b\d+(?:\.\d+)?\s*W\b",
    r"\bM10\b|\bM10Q\b|\bM8N\b|\bM9N\b|\bF9P\b|\bRTK\b",
    r"\bO3\b|\bO4(?:\s*Pro)?\b|\bAvatar\b|\bWalksnail\b|\bHDZero\b|\bAnalog\b|\bStarlight\b|\b\d{3,4}\s*TVL\b|\b4K\b",
    r"\b30\.5\s*x\s*30\.5\b|\b20\s*x\s*20\b|\b25\.5\s*x\s*25\.5\b",
    r"\bXT30\b|\bXT60\b|\bXT90\b|\bAS150\b|\bSMA\b|\bRP-SMA\b|\bMMCX\b|\bU\.?FL\b|\bLHCP\b|\bRHCP\b",
    r"\bHall\s*Gimbal\b|\bAG01\b|\bEdgeTX\b"
]

# ----------------- IMAGE & INVALID URL HELPER -----------------
def is_image_or_invalid_product_link(title: str, url: str) -> bool:
    """Rejects image links, 'Image 146' markdown labels, and non-product URLs."""
    t_low = title.lower().strip()
    u_low = url.lower().strip()

    # 1. Reject titles that are actually image alt-tags (e.g., "Image 146", "!Image 12", "IMG_2024")
    if re.match(r"^!?\s*(?:image|img|photo|picture|pic|banner|logo|icon|thumbnail|untitled)\b", t_low):
        return True
    if re.search(r"\.(?:jpg|jpeg|png|webp|gif|svg|bmp|pdf)$", t_low):
        return True

    # 2. Reject URLs that point to image files or static CDN assets
    if re.search(r"\.(?:jpg|jpeg|png|webp|gif|svg|bmp|ico|pdf|css|js)(?:\?.*)?$", u_low):
        return True
    if any(img_pat in u_low for img_pat in [
        "notion.site/image/", "/_next/image", "/wp-content/uploads/",
        "cloudinary.com", "amazonaws.com", "/cdn/shop/files/", "/cdn/shop/products/",
        "facebook.com", "instagram.com", "twitter.com", "linkedin.com", "youtube.com",
        "/cart", "/checkout", "/my-account", "/login", "/wishlist", "add-to-cart=",
        "/tag/", "/blog/", "javascript:", "mailto:", "tel:"
    ]):
        return True

    return False

# ----------------- STEP 1: AI-ASSISTED HARDWARE ADVISOR & TECHNICAL LOCK PLANNER -----------------
def understand_user_query(raw_query: str, api_key: str = "") -> dict:
    q_clean = re.sub(r"[^a-zA-Z0-9\.\-\"]", " ", raw_query).strip()
    q_lower = q_clean.lower()

    # Check if query is an overly general single-category word (e.g., just "brushless motor")
    triage_info = None
    for term, t_map in EXTREMELY_GENERAL_MAP.items():
        if any(re.search(pat, q_lower) for pat in t_map["patterns"]):
            triage_info = t_map
            break

    # 1. Detect Primary Category & Exclusions
    detected_category = "General Drone Component"
    category_exclusions = set()
    for cat_name, patterns, exclusions in CATEGORY_RULES:
        if any(re.search(pat, q_lower) for pat in patterns):
            detected_category = cat_name
            category_exclusions = set(exclusions)
            break

    # 2. Extract Strict Technical Locks from User Query (Stator, KV, Voltage, Amperage)
    # Example: "3115 900kv motor" -> locked_stator = "3115", locked_kv = "900"
    locked_stators = [s for s in ALL_KNOWN_STATORS if re.search(rf"\b{re.escape(s)}\b", q_lower)]
    kv_matches = re.findall(r"\b(\d{3,5})\s*kv\b", q_lower)
    locked_kvs = list(dict.fromkeys(kv_matches))
    cell_matches = re.findall(r"\b([1-8]s)\b", q_lower)
    locked_cells = list(dict.fromkeys(cell_matches))

    # 3. Check Size/Build-Class Assisted Queries (ONLY if user didn't already specify an exact stator/KV)
    ai_explanation = ""
    search_queries = []
    must_type_tokens = []
    any_spec_tokens = []
    is_ai_expanded = False

    comp_key = None
    if re.search(r"\bmotors?\b|\bkv\b|\bbldc\b", q_lower):
        comp_key = "motor"
    elif re.search(r"\bframes?\b|\bkit\b|\bwhoop\b|\bcinewhoop\b|\bchassis\b", q_lower):
        comp_key = "frame"
    elif re.search(r"\bprops?\b|\bpropellers?\b|\bblades?\b", q_lower):
        comp_key = "prop"
    elif re.search(r"\bstack\b|\bfc\b|\bflight controller\b|\besc\b", q_lower):
        comp_key = "stack"
    elif re.search(r"\bbattery\b|\bbatteries\b|\blipo\b|\bmah\b", q_lower):
        comp_key = "battery"

    # Only use broad size-class expansion when user didn't lock a specific stator or KV
    if comp_key and not locked_stators and not locked_kvs:
        for size_class, size_data in DRONE_SIZE_COMPATIBILITY.items():
            if any(re.search(pat, q_lower) for pat in size_data["size_patterns"]):
                if comp_key in size_data:
                    rule = size_data[comp_key]
                    ai_explanation = rule["explanation"]
                    search_queries = list(rule["search_queries"])
                    must_type_tokens = list(rule["type_tokens"])
                    any_spec_tokens = list(rule["spec_tokens"])
                    is_ai_expanded = True
                    break

    # 4. Functional Beginner Queries
    if not is_ai_expanded and not locked_stators and not locked_kvs:
        if re.search(r"\blong\s*range\s*(?:rx|receiver)\b", q_lower):
            detected_category = "FPV / RC Receiver (RX)"
            ai_explanation = "Long-Range Telemetry Receivers -> 900MHz / 915MHz ELRS, TBS Crossfire, & Diversity Receivers"
            search_queries = ["915mhz receiver", "elrs 900 rx", "crossfire nano rx", "superd receiver"]
            must_type_tokens = ["receiver", "rx", "nano", "superd", "superp", "rp", "xr"]
            any_spec_tokens = ["915", "900", "868", "crossfire", "diversity", "elrs", "expresslrs"]
            is_ai_expanded = True
        elif re.search(r"\bautopilot\b|\bautonomous\s*flight\s*controller\b", q_lower):
            detected_category = "Flight Controller / FC Stack / Autopilot"
            ai_explanation = "Autonomous Autopilots -> Pixhawk, Cube Orange, Matek H743, CUAV, JIYI K++"
            search_queries = ["pixhawk", "cube orange", "h743 flight controller", "cuav", "jiyi k++"]
            must_type_tokens = ["pixhawk", "cube", "h743", "cuav", "autopilot", "flight controller", "jiyi"]
            any_spec_tokens = ["pixhawk", "cube", "h743", "f405-wte", "f405-wing", "cuav", "jiyi", "ardupilot"]
            is_ai_expanded = True

    # 5. Specific Technical / Model Query (e.g., "3115 900kv motor", "Radiomaster Pocket")
    stop_words = {
        "for", "with", "and", "the", "in", "of", "to", "a", "an", "drone",
        "fpv", "rc", "buy", "india", "online", "best", "compatible", "inch"
    }
    raw_tokens = [t.strip("\"''") for t in q_lower.split() if len(t.strip("\"''")) >= 2 and t.strip("\"''") not in stop_words]
    if not raw_tokens:
        raw_tokens = [t for t in q_lower.split() if t]

    if not is_ai_expanded:
        search_queries = [q_clean]
        # Smart fan-out for Stator + KV queries (e.g. "3115 900kv motor" -> also search "3115 900kv", "3115-900kv", "3115 motor")
        if locked_stators and locked_kvs:
            stator = locked_stators[0]
            kv = locked_kvs[0]
            search_queries = [
                f"{stator} {kv}kv",
                f"{stator}-{kv}kv",
                f"{stator} {kv}kv motor",
                f"{stator} motor"
            ]
            ai_explanation = f"Precision Spec Lock -> Stator: {stator} | Rating: {kv}KV ({detected_category})"
        elif locked_stators:
            stator = locked_stators[0]
            search_queries = [f"{stator} motor", stator]
            ai_explanation = f"Precision Stator Lock -> Stator: {stator} ({detected_category})"
        else:
            if " " in q_clean and len(raw_tokens) == 2:
                search_queries.append("".join(raw_tokens))
            ai_explanation = f"Direct Component Search ({detected_category})"

    # Deduplicate search queries
    dedup_queries = []
    for sq in search_queries:
        if sq.strip() and sq.strip().lower() not in [x.lower() for x in dedup_queries]:
            dedup_queries.append(sq.strip())
    dedup_queries = dedup_queries[:8]

    # Identify Conflicting Sibling Models & Stators
    conflicting_tokens = set()
    if not is_ai_expanded:
        q_nospace = q_lower.replace(" ", "")
        for group in MODEL_CONFLICT_GROUPS:
            matched_in_group = {
                t for t in group
                if re.search(rf"\b{re.escape(t)}\b", q_lower) or (len(t) >= 4 and t in q_nospace)
            }
            if matched_in_group:
                conflicting_tokens.update(group - matched_in_group)

    # Exclusions pool setup
    user_wants_accessory = any(re.search(rf"\b{re.escape(w)}\b", q_lower) for w in GENERAL_ACCESSORY_WORDS)
    active_exclusions = set()
    if not user_wants_accessory:
        active_exclusions.update(GENERAL_ACCESSORY_WORDS)
    for exc in category_exclusions:
        if exc not in q_lower:
            active_exclusions.add(exc)

    return {
        "raw_query": raw_query.strip(),
        "search_term": dedup_queries[0] if dedup_queries else q_clean,
        "search_queries": dedup_queries,
        "category": detected_category,
        "ai_explanation": ai_explanation,
        "is_ai_expanded": is_ai_expanded,
        "is_extremely_general": triage_info is not None,
        "triage_info": triage_info,
        "locked_stators": locked_stators,
        "locked_kvs": locked_kvs,
        "locked_cells": locked_cells,
        "must_tokens": raw_tokens,
        "must_type_tokens": must_type_tokens,
        "any_spec_tokens": any_spec_tokens,
        "conflicting_tokens": conflicting_tokens,
        "exclude_words": active_exclusions,
    }

# ----------------- STEP 2: STRICT TECHNICAL INTENT VERIFIER -----------------
def verify_product_matches_intent(title: str, intent: dict, extra_context: str = "", url: str = "") -> tuple[bool, int]:
    if not title or len(title.strip()) < 5:
        return False, 0

    # 1. Block all Image links, 'Image 146' markdown labels, and static file URLs
    if is_image_or_invalid_product_link(title, url):
        return False, 0

    t_lower = title.lower().strip()
    t_compact = re.sub(r"[\s\-_]", "", t_lower)

    # 2. Block navigation labels
    nav_blacklist = {
        "home", "shop", "cart", "view cart", "add to cart", "checkout", "my account",
        "login", "register", "wishlist", "compare", "track order", "contact us",
        "about us", "privacy policy", "terms and conditions", "read more", "search",
        "frames", "motors", "propellers", "view details"
    }
    if t_lower in nav_blacklist or re.match(r"^\d+(\.\d+)?\"?\s*frames$", t_lower):
        return False, 0

    # 3. Block Non-Drone / Industrial / E-Bike Motors (e.g., E-BIKE MY1016, 775 motor, BO motor)
    for bad_term in NON_DRONE_BLACKLIST:
        if bad_term in t_lower:
            return False, 0

    # 4. Block excluded accessory / spare-part words in the product title
    for exc in intent["exclude_words"]:
        if re.search(rf"\b{re.escape(exc)}\b", t_lower):
            return False, 0

    # 5. STRICT TECHNICAL SPEC LOCKS (Stator & KV Enforcement in Title!)
    # If user typed a stator (e.g. 3115), the product title MUST contain 3115
    if intent.get("locked_stators"):
        for req_stator in intent["locked_stators"]:
            if not re.search(rf"(?:^|[^0-9]){re.escape(req_stator)}(?:[^0-9]|$)", t_lower):
                return False, 0

    # If user typed a KV rating (e.g. 900kv), the product title or snippet MUST match that exact KV,
    # and if the title lists any OTHER KV rating (like 2300KV or 800KV), REJECT IT!
    if intent.get("locked_kvs"):
        req_kvs = set(intent["locked_kvs"])
        title_kvs = set(re.findall(r"(\d{3,5})\s*kv\b", t_lower))
        if title_kvs:
            if not (req_kvs & title_kvs):
                return False, 0
        else:
            # If KV isn't written with 'KV' suffix, check for patterns like '3115-900' or '900kv' in snippet
            kv_matched = False
            for r_kv in req_kvs:
                if re.search(rf"\b{re.escape(r_kv)}\s*kv\b", extra_context.lower()) or re.search(rf"[\-\s]{re.escape(r_kv)}\b", t_lower):
                    kv_matched = True
                    break
            if not kv_matched:
                return False, 0

    q_lower = intent["raw_query"].lower()

    # 6A. Matching Mode for AI-Expanded Size/Class Queries (e.g., "5 inch FPV motors", "2.5 inch frame")
    if intent.get("is_ai_expanded"):
        combined_lower = f"{t_lower} {extra_context.lower()}"
        combined_compact = re.sub(r"[\s\-_]", "", combined_lower)

        type_ok = any(tok in t_lower or re.sub(r"[\s\-_]", "", tok) in t_compact for tok in intent["must_type_tokens"])
        if not type_ok:
            return False, 0

        if re.search(r"\b(?:bearing|shaft|screw|bell|mount|guard|strap|tpu|arm|plate|canopy)\b.*\bfor\b", t_lower):
            return False, 0

        spec_in_title = any(
            spec in t_lower or re.sub(r"[\s\-_]", "", spec) in t_compact
            for spec in intent["any_spec_tokens"]
        )
        spec_in_context = any(
            spec in combined_lower or re.sub(r"[\s\-_]", "", spec) in combined_compact
            for spec in intent["any_spec_tokens"]
        )

        if not (spec_in_title or spec_in_context):
            return False, 0

        score = 130 if spec_in_title else 95
        if q_lower in t_lower:
            score += 40
        return True, score

    # 6B. Matching Mode for Specific Queries (e.g., "3115 900kv motor", "Radiomaster Pocket")
    # CRITICAL FIX: Match mandatory tokens strictly against TITLE (`t_lower` / `t_compact`), NEVER against search URL!
    if " for " not in q_lower:
        parts_split = re.split(r"\b(?:for|compatible\s+with|suitable\s+for|fits|replacement\s+for)\b", t_lower, maxsplit=1)
        if len(parts_split) == 2:
            prefix_part, suffix_part = parts_split[0], parts_split[1]
            for must_tok in intent["must_tokens"]:
                if len(must_tok) >= 4 and must_tok in suffix_part and must_tok not in prefix_part:
                    return False, 0

    for tok in intent["must_tokens"]:
        # If this token is "motor" and the title already matched a locked stator + KV (e.g. "BrotherHobby Avenger 3115 900KV"), allow it
        if tok in ("motor", "motors") and (intent.get("locked_stators") or intent.get("locked_kvs")):
            continue
        synonyms = SYNONYM_GROUPS.get(tok, [tok])
        tok_matched = False
        for syn in synonyms:
            syn_compact = re.sub(r"[\s\-_]", "", syn)
            if syn in t_lower or syn_compact in t_compact:
                tok_matched = True
                break
        if not tok_matched:
            return False, 0

    # Reject any conflicting model or stator in the title (e.g., rejects 2205 or 3110 when searching 3115)
    for conflict in intent["conflicting_tokens"]:
        if re.search(rf"(?:^|[^0-9a-z]){re.escape(conflict)}(?:[^0-9a-z]|$)", t_lower):
            return False, 0

    score = 120
    if q_lower in t_lower:
        score += 50
    if intent["must_tokens"] and t_lower.startswith(intent["must_tokens"][0]):
        score += 25
    score -= max(0, (len(t_lower) - 45) // 5)

    return True, score

# ----------------- BRAND & SPEC EXTRACTION -----------------
def detect_brand(title: str, default_brand: str = "") -> str:
    if default_brand and default_brand.lower() not in ["generic", "unknown", "n/a", "image", ""]:
        alias_check = BRAND_ALIASES.get(default_brand.lower().strip())
        return alias_check if alias_check else default_brand

    t_lower = title.lower()
    for brand in KNOWN_BRANDS:
        b_low = brand.lower()
        if re.search(rf"\b{re.escape(b_low)}\b", t_lower) or b_low in t_lower:
            return BRAND_ALIASES.get(b_low, brand)

    first_word = re.sub(r"[^a-zA-Z0-9\-]", "", title.strip().split()[0]) if title.strip() else "Generic"
    return first_word if len(first_word) > 2 else "Generic"

def extract_specs_from_title(title: str, extra_desc: str = "") -> str:
    # Extract specs primarily from the product title so neighbor items don't pollute the spec column
    found = []
    for pat in SPEC_PATTERNS:
        for m in re.findall(pat, title, re.I):
            clean_m = m.strip()
            if clean_m.upper() not in [x.upper() for x in found]:
                found.append(clean_m)
    if len(found) < 2 and extra_desc:
        for pat in SPEC_PATTERNS:
            for m in re.findall(pat, extra_desc[:200], re.I):
                clean_m = m.strip()
                if clean_m.upper() not in [x.upper() for x in found]:
                    found.append(clean_m)
    if found:
        return " · ".join(found[:6])
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

# ----------------- PARSE / DEEP WEB SCRAPING -----------------
def parse_danny_notion_listing(md_text: str, intent: dict) -> list[dict]:
    """
    Dedicated parser for Danny's Notion Inventory List.
    Strips all ![Image ...] tags and only matches genuine text product rows with prices.
    """
    items = []
    # Remove markdown image references completely
    cleaned_md = re.sub(r"!?\[(?:Image\s*\d*[^\]]*)\]\([^\)]+\)", "", md_text, flags=re.I)
    lines = [l.strip() for l in cleaned_md.splitlines() if l.strip()]

    for i, line in enumerate(lines):
        # Skip short lines or pure price lines
        if len(line) < 8 or re.match(r"^(?:₹|Rs\.?)\s*[0-9,]+", line, re.I):
            continue
        clean_title = re.sub(r"^(?:####+|###+|\*+|\-+)\s*", "", line).strip()
        is_match, score = verify_product_matches_intent(clean_title, intent, "", DANNY_NOTION_URL)
        if not is_match:
            continue

        # Look at current line + next 2 lines for price
        window = " ".join(lines[i:min(len(lines), i + 3)])
        if re.search(r"\bout of stock\b|\bsold out\b", window, re.I):
            continue
        price = parse_inr_price(window)
        if price > 0:
            items.append({
                "product_name": clean_title,
                "specification": extract_specs_from_title(clean_title, ""),
                "brand_name": detect_brand(clean_title),
                "vendor_name": "Danny’s Inventory List",
                "sku_name": "N/A",
                "rate": price,
                "in_stock": True,
                "link": DANNY_NOTION_URL,
                "relevance": score
            })
    return items

def parse_markdown_listing(md_text: str, vendor: str, base_url: str, intent: dict) -> list[dict]:
    if vendor == "Danny’s Inventory List":
        return parse_danny_notion_listing(md_text, intent)

    items = []
    # Strip markdown image tags first so `[![Image 146](img.jpg)](prod_url)` becomes `[](prod_url)` or clean text
    cleaned_md = re.sub(r"!\[[^\]]*\]\([^\)]+\)", "", md_text)
    lines = [l.strip() for l in cleaned_md.splitlines() if l.strip()]

    for i, line in enumerate(lines):
        for m in re.finditer(r"\[([^\[\]]+)\]\((https?://[^\s\)]+)\)", line):
            raw_title = m.group(1).strip()
            url = m.group(2).strip()

            clean_title = re.sub(r"^(?:####+|###+|\*+|\-+)\s*", "", raw_title).strip()
            clean_title = re.sub(r"(?:Add to cart|Add to Wishlist|Add to Compare|Quick View).*$", "", clean_title, flags=re.I).strip()

            if is_image_or_invalid_product_link(clean_title, url):
                continue

            end_idx = min(len(lines), i + 5)
            window_lines = [lines[i]]
            for j in range(i + 1, end_idx):
                if re.search(r"\[([^\[\]]{10,})\]\((https?://[^\s\)]+)\)", lines[j]):
                    break
                window_lines.append(lines[j])
            window_blob = " \n ".join(window_lines)

            if re.search(r"\bout of stock\b|\bsold out\b|\bcurrently unavailable\b", window_blob, re.I):
                continue

            is_match, score = verify_product_matches_intent(clean_title, intent, window_blob, url)
            if not is_match:
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
        ".product-item, .product-card, .product-layout, .productListing-odd, .productListing-even, "
        ".theme-product-box, .zpro-product"
    )

    for card in cards:
        card_text = card.get_text(" ", strip=True)
        if re.search(r"\bout of stock\b|\bsold out\b", card_text, re.I) or "out-of-stock" in " ".join(card.get("class", [])):
            continue

        title_el = card.select_one(
            ".woocommerce-loop-product__title, .product-title, .name, "
            "h2 a, h3 a, h4 a, h2, h3, h4, a.woocommerce-LoopProduct-link"
        )
        if not title_el:
            continue
        title = title_el.get_text(" ", strip=True)

        a_tag = title_el if title_el.name == "a" else card.select_one("a[href]")
        link = a_tag["href"] if a_tag and a_tag.has_attr("href") else base_url
        if link.startswith("/"):
            link = f"{base_url.rstrip('/')}{link}"

        if is_image_or_invalid_product_link(title, link):
            continue

        is_match, score = verify_product_matches_intent(title, intent, card_text, link)
        if not is_match:
            continue

        sku_el = card.select_one(".sku, .product-sku")
        sku = sku_el.get_text(strip=True).replace("SKU:", "").strip() if sku_el else "N/A"
        if sku == "N/A":
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

async def crawl_category_or_collection_url(
    session: httpx.AsyncClient, jina_sem: asyncio.Semaphore,
    vendor: str, cat_url: str, base_url: str, intent: dict
) -> list[dict]:
    extracted = []
    try:
        resp = await session.get(cat_url, headers=BROWSER_HEADERS, timeout=9.0)
        if resp.status_code == 200 and len(resp.text) > 500:
            extracted.extend(parse_html_dom(resp.text, vendor, base_url, intent))
    except Exception:
        pass
    if not extracted:
        md_text = await fetch_via_jina(session, jina_sem, cat_url)
        if md_text:
            extracted.extend(parse_markdown_listing(md_text, vendor, base_url, intent))
    return extracted

async def fetch_multi_engine_web_index(
    session: httpx.AsyncClient, search_sem: asyncio.Semaphore, jina_sem: asyncio.Semaphore,
    vendor: str, domain: str, base_url: str, intent: dict
) -> list[dict]:
    items = []
    category_urls_to_follow = set()
    queries_to_run = [intent["raw_query"]]
    for sq in intent["search_queries"][:2]:
        if sq.lower() not in [x.lower() for x in queries_to_run]:
            queries_to_run.append(sq)

    async with search_sem:
        for q_str in queries_to_run[:2]:
            site_q = f"site:{domain} {q_str}"

            y_url = f"https://in.search.yahoo.com/search?p={quote_plus(site_q)}&n=15"
            try:
                resp = await session.get(y_url, headers=BROWSER_HEADERS, timeout=9.0)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for algo in soup.select("div.algo, div.Sr"):
                        a_el = algo.select_one("h3 a, a")
                        snip_el = algo.select_one(".compText, p")
                        if not a_el:
                            continue
                        raw_title = a_el.get_text(" ", strip=True)
                        href = a_el.get("href", "")
                        if "RU=" in href:
                            href = unquote(href.split("RU=")[1].split("/RK=")[0])

                        if domain not in href.lower():
                            continue

                        if any(c_pat in href.lower() for c_pat in ["/product-category/", "/collections/", "/category/"]):
                            category_urls_to_follow.add(href)
                            continue

                        clean_title = re.split(
                            r"\s+[\-\|–]\s+(?:Buy|Robu|Zbotic|Quadkart|Design Info|Indian Robo|Robokits|Xrobo|Tujo|Anubis|FPV|Hi Tech|UAV)",
                            raw_title, flags=re.I
                        )[0].strip()

                        if is_image_or_invalid_product_link(clean_title, href):
                            continue

                        snippet = snip_el.get_text(" ", strip=True) if snip_el else ""
                        if re.search(r"\bout of stock\b|\bsold out\b", f"{clean_title} {snippet}", re.I):
                            continue

                        is_match, score = verify_product_matches_intent(clean_title, intent, snippet, href)
                        if not is_match:
                            continue

                        sku_m = re.search(r"SKU\s*[:#\-]?\s*([A-Za-z0-9_\-]+)", f"{clean_title} {snippet}", re.I)
                        items.append({
                            "product_name": clean_title,
                            "specification": extract_specs_from_title(clean_title, snippet),
                            "brand_name": detect_brand(clean_title),
                            "vendor_name": vendor,
                            "sku_name": sku_m.group(1) if sku_m else "N/A",
                            "rate": parse_inr_price(f"{clean_title} {snippet}"),
                            "in_stock": True,
                            "link": href,
                            "relevance": score
                        })
            except Exception:
                pass

    for cat_url in list(category_urls_to_follow)[:2]:
        items.extend(await crawl_category_or_collection_url(session, jina_sem, vendor, cat_url, base_url, intent))

    return items

async def scrape_woocommerce_vendor(
    session: httpx.AsyncClient, search_sem: asyncio.Semaphore, jina_sem: asyncio.Semaphore,
    vendor: str, base_url: str, intent: dict
) -> list[dict]:
    found_items = []
    queries = intent["search_queries"]

    async def fetch_wc_api_single(q: str) -> list[dict]:
        q_items = []
        api_url = f"{base_url}/wp-json/wc/store/v1/products?search={quote_plus(q)}&per_page=25"
        try:
            resp = await session.get(api_url, timeout=8.0)
            if resp.status_code == 200 and "application/json" in resp.headers.get("content-type", ""):
                data = resp.json()
                if isinstance(data, list):
                    for item in data:
                        if not item.get("is_in_stock", True):
                            continue
                        title = BeautifulSoup(item.get("name", ""), "html.parser").get_text(" ", strip=True)
                        short_desc = BeautifulSoup(item.get("short_description", ""), "html.parser").get_text(" ", strip=True)
                        permalink = item.get("permalink", base_url)
                        is_match, score = verify_product_matches_intent(title, intent, short_desc, permalink)
                        if not is_match:
                            continue
                        prices = item.get("prices", {})
                        raw_price = prices.get("price", "0")
                        minor_unit = prices.get("currency_minor_unit", 2)
                        q_items.append({
                            "product_name": title,
                            "specification": extract_specs_from_title(title, short_desc),
                            "brand_name": detect_brand(title),
                            "vendor_name": vendor,
                            "sku_name": item.get("sku") or "N/A",
                            "rate": float(raw_price) / (10 ** minor_unit) if raw_price else 0.0,
                            "in_stock": True,
                            "link": permalink,
                            "relevance": score
                        })
        except Exception:
            pass
        return q_items

    wc_batches = await asyncio.gather(*(fetch_wc_api_single(q) for q in queries[:6]), return_exceptions=True)
    for b in wc_batches:
        if isinstance(b, list):
            found_items.extend(b)

    if len(found_items) < 2:
        for q in queries[:2]:
            search_url = f"{base_url}/?s={quote_plus(q)}&post_type=product"
            try:
                resp = await session.get(search_url, timeout=9.0)
                if resp.status_code == 200 and len(resp.text) > 500:
                    found_items.extend(parse_html_dom(resp.text, vendor, base_url, intent))
            except Exception:
                pass

    if len(found_items) < 2:
        for q in queries[:2]:
            search_url = f"{base_url}/?s={quote_plus(q)}&post_type=product"
            md_text = await fetch_via_jina(session, jina_sem, search_url)
            if md_text:
                found_items.extend(parse_markdown_listing(md_text, vendor, base_url, intent))

    if (intent.get("is_ai_expanded") or len(found_items) < 3) and vendor in VENDOR_DOMAINS:
        found_items.extend(await fetch_multi_engine_web_index(
            session, search_sem, jina_sem, vendor, VENDOR_DOMAINS[vendor], base_url, intent
        ))

    return found_items

async def scrape_shopify_vendor(
    session: httpx.AsyncClient, search_sem: asyncio.Semaphore, jina_sem: asyncio.Semaphore,
    vendor: str, base_url: str, intent: dict
) -> list[dict]:
    found_items = []
    queries = intent["search_queries"]

    async def fetch_shopify_single(q: str) -> list[dict]:
        q_items = []
        api_url = f"{base_url}/search/suggest.json?q={quote_plus(q)}&resources[type]=product&resources[limit]=20"
        try:
            resp = await session.get(api_url, timeout=8.0)
            if resp.status_code == 200:
                data = resp.json()
                products = data.get("resources", {}).get("results", {}).get("products", [])
                for p in products:
                    if not p.get("available", True):
                        continue
                    title = p.get("title", "")
                    body_text = BeautifulSoup(p.get("body", ""), "html.parser").get_text(" ", strip=True)
                    prod_url = f"{base_url}{p.get('url', '')}"
                    is_match, score = verify_product_matches_intent(title, intent, body_text, prod_url)
                    if not is_match:
                        continue
                    sku = p.get("variants", [{}])[0].get("sku") if p.get("variants") else "N/A"
                    q_items.append({
                        "product_name": title,
                        "specification": extract_specs_from_title(title, body_text),
                        "brand_name": detect_brand(title, p.get("vendor", "")),
                        "vendor_name": vendor,
                        "sku_name": sku if sku else "N/A",
                        "rate": float(p.get("price", 0)),
                        "in_stock": True,
                        "link": prod_url,
                        "relevance": score
                    })
        except Exception:
            pass
        return q_items

    sh_batches = await asyncio.gather(*(fetch_shopify_single(q) for q in queries[:5]), return_exceptions=True)
    for b in sh_batches:
        if isinstance(b, list):
            found_items.extend(b)

    if (intent.get("is_ai_expanded") or len(found_items) < 3) and vendor in VENDOR_DOMAINS:
        found_items.extend(await fetch_multi_engine_web_index(
            session, search_sem, jina_sem, vendor, VENDOR_DOMAINS[vendor], base_url, intent
        ))

    return found_items

async def scrape_custom_or_notion_vendor(
    session: httpx.AsyncClient, search_sem: asyncio.Semaphore, jina_sem: asyncio.Semaphore,
    vendor: str, search_prefix: str, intent: dict
) -> list[dict]:
    found_items = []
    queries = intent["search_queries"] if vendor != "Danny’s Inventory List" else [""]
    base_domain_url = f"https://{VENDOR_DOMAINS[vendor]}" if vendor in VENDOR_DOMAINS else search_prefix

    for q in queries[:3]:
        target_url = f"{search_prefix}{quote_plus(q)}" if vendor != "Danny’s Inventory List" else DANNY_NOTION_URL
        if vendor != "Danny’s Inventory List":
            try:
                resp = await session.get(target_url, timeout=9.0)
                if resp.status_code == 200 and len(resp.text) > 500:
                    found_items.extend(parse_html_dom(resp.text, vendor, base_domain_url, intent))
            except Exception:
                pass

        if not found_items:
            md_text = await fetch_via_jina(session, jina_sem, target_url)
            if md_text:
                found_items.extend(parse_markdown_listing(md_text, vendor, base_domain_url, intent))

    if (intent.get("is_ai_expanded") or len(found_items) < 2) and vendor in VENDOR_DOMAINS:
        found_items.extend(await fetch_multi_engine_web_index(
            session, search_sem, jina_sem, vendor, VENDOR_DOMAINS[vendor], base_domain_url, intent
        ))

    return found_items

async def run_all_scrapers(intent: dict, selected_vendors: list[str]) -> list[dict]:
    jina_sem = asyncio.Semaphore(4)
    search_sem = asyncio.Semaphore(4)
    all_items = []

    async with httpx.AsyncClient(headers=BROWSER_HEADERS, follow_redirects=True) as session:
        tasks = []
        for vendor, url in WOOCOMMERCE_VENDORS.items():
            if vendor in selected_vendors:
                tasks.append(scrape_woocommerce_vendor(session, search_sem, jina_sem, vendor, url, intent))

        for vendor, url in SHOPIFY_VENDORS.items():
            if vendor in selected_vendors:
                tasks.append(scrape_shopify_vendor(session, search_sem, jina_sem, vendor, url, intent))

        for vendor, search_prefix in CUSTOM_VENDORS.items():
            if vendor in selected_vendors:
                tasks.append(scrape_custom_or_notion_vendor(session, search_sem, jina_sem, vendor, search_prefix, intent))

        if "Danny’s Inventory List" in selected_vendors:
            tasks.append(scrape_custom_or_notion_vendor(session, search_sem, jina_sem, "Danny’s Inventory List", DANNY_NOTION_URL, intent))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in results:
            if isinstance(res, list):
                all_items.extend(res)

    by_link = {}
    for item in all_items:
        clean_link = item["link"].split("?")[0].rstrip("/").lower()
        key = clean_link if clean_link != DANNY_NOTION_URL.lower() else f"danny_{item['product_name'].lower()}"
        if key not in by_link:
            by_link[key] = item
        else:
            if by_link[key]["rate"] == 0 and item["rate"] > 0:
                by_link[key] = item
            elif by_link[key]["sku_name"] == "N/A" and item["sku_name"] != "N/A":
                by_link[key]["sku_name"] = item["sku_name"]

    return list(by_link.values())

# ----------------- EXPORT TO XLSX (.XLSX) -----------------
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

# ----------------- SESSION STATE -----------------
if "boq_cart" not in st.session_state:
    st.session_state.boq_cart = []
if "search_results" not in st.session_state:
    st.session_state.search_results = []
if "last_intent" not in st.session_state:
    st.session_state.last_intent = None
if "active_query" not in st.session_state:
    st.session_state.active_query = ""

# ----------------- SIDEBAR SETTINGS -----------------
with st.sidebar:
    st.markdown("### ⚙️ Search Configuration")
    api_key = st.text_input(
        "Gemini API Key (Optional)",
        value=st.secrets.get("GEMINI_API_KEY", "") if "GEMINI_API_KEY" in st.secrets else "",
        type="password",
    )
    all_vendor_names = list(WOOCOMMERCE_VENDORS.keys()) + list(SHOPIFY_VENDORS.keys()) + list(CUSTOM_VENDORS.keys()) + ["Danny’s Inventory List"]
    selected_vendors = st.multiselect("Stores to search", options=all_vendor_names, default=all_vendor_names)
    hide_zero_price = st.checkbox("Hide items without prices", value=False)

# ----------------- CRASH-PROOF BRAND LOGO & HEADER -----------------
def load_valid_logo():
    for filename in ["image_5.png", "logo.png", "logo.jpg", "logo.jpeg", "logo.webp"]:
        if os.path.exists(filename) and os.path.getsize(filename) > 100:
            try:
                img = Image.open(filename)
                img.verify()
                return Image.open(filename)
            except Exception:
                continue
    return None

FALLBACK_LOGO_SVG = """
<div style="display:flex; align-items:center; justify-content:center; padding: 6px 0;">
    <svg viewBox="0 0 260 190" width="100%" style="max-width:190px; height:auto;" xmlns="http://www.w3.org/2000/svg">
        <circle cx="130" cy="95" r="78" fill="none" stroke="#00B4D8" stroke-width="4" stroke-dasharray="180 40 90 30"/>
        <circle cx="130" cy="95" r="68" fill="none" stroke="#F77F00" stroke-width="3.5" stroke-dasharray="120 50 140 40"/>
        <ellipse cx="130" cy="95" rx="92" ry="34" fill="none" stroke="#00B4D8" stroke-width="3.5" transform="rotate(-35 130 95)"/>
        <ellipse cx="130" cy="95" rx="92" ry="34" fill="none" stroke="#F77F00" stroke-width="3" transform="rotate(35 130 95)"/>
        <circle cx="192" cy="40" r="6" fill="#00B4D8"/>
        <circle cx="68" cy="150" r="6" fill="#F77F00"/>
        <path d="M 130 37 A 58 58 0 0 0 130 153 Z" fill="none" stroke="#00B4D8" stroke-width="10" stroke-dasharray="14 8"/>
        <path d="M 130 37 A 58 58 0 0 1 130 153 Z" fill="none" stroke="#F77F00" stroke-width="10" stroke-dasharray="14 8"/>
        <path d="M 102 67 L 158 123 M 158 67 L 102 123" stroke="#00B4D8" stroke-width="9" stroke-linecap="round"/>
        <circle cx="130" cy="95" r="14" fill="#FFFFFF" stroke="#F77F00" stroke-width="5"/>
        <circle cx="100" cy="65" r="16" fill="#FFFFFF" stroke="#F77F00" stroke-width="4.5"/>
        <circle cx="160" cy="65" r="16" fill="#FFFFFF" stroke="#F77F00" stroke-width="4.5"/>
        <circle cx="100" cy="125" r="16" fill="#FFFFFF" stroke="#F77F00" stroke-width="4.5"/>
        <circle cx="160" cy="125" r="16" fill="#FFFFFF" stroke="#F77F00" stroke-width="4.5"/>
        <circle cx="100" cy="65" r="5" fill="#00B4D8"/>
        <circle cx="160" cy="65" r="5" fill="#00B4D8"/>
        <circle cx="100" cy="125" r="5" fill="#00B4D8"/>
        <circle cx="160" cy="125" r="5" fill="#00B4D8"/>
    </svg>
</div>
"""

logo_col, title_col = st.columns([1.1, 4.3])
with logo_col:
    valid_logo = load_valid_logo()
    if valid_logo is not None:
        st.image(valid_logo, use_container_width=True)
    else:
        st.markdown(FALLBACK_LOGO_SVG, unsafe_allow_html=True)

with title_col:
    st.markdown("""
    <div style="padding-top: 12px;">
        <div class="app-title">
            <span style="color:#00A8E8;">The Drone</span> <span style="color:#F77F00;">Builder</span>
            <span style="color:#0F172A; font-weight:600; font-size:1.25rem;"> — AI-Assisted Vendor Search & BOQ Builder</span>
        </div>
        <p class="app-subtitle" style="color:#D97706; font-weight:600; letter-spacing:0.08em; text-transform:uppercase; font-size:0.82rem; margin-top:4px;">
            INNOVATING THE PART SELECTION PROCESS
        </p>
    </div>
    """, unsafe_allow_html=True)

# ----------------- DIRECT SEARCH INPUT -----------------
search_col, btn_col = st.columns([5, 1.2])
with search_col:
    query_input = st.text_input(
        "Search drone component",
        value=st.session_state.active_query,
        placeholder="Try '3115 900kv motor', '5 inch FPV motors', '2.5 inch frame', or 'brushless motor'...",
        label_visibility="collapsed"
    )
with btn_col:
    run_search = st.button("🔍 Search Vendors", type="primary", use_container_width=True)

# Pre-screen for general triage queries
pre_screen_intent = understand_user_query(query_input.strip(), api_key) if query_input.strip() else None

if pre_screen_intent and pre_screen_intent.get("is_extremely_general"):
    triage = pre_screen_intent["triage_info"]
    st.markdown(f"""
    <div class="triage-card">
        <div class="triage-title">🎯 Technical Triage Assistant: Select Your Drone Class</div>
        <p style="margin:0;">{triage['message']}</p>
    </div>
    """, unsafe_allow_html=True)

    triage_cols = st.columns(3)
    idx = 0
    for label, payload in triage["categories"].items():
        with triage_cols[idx % 3]:
            if st.button(f"🎯 {label}\n({payload['subtext']})", use_container_width=True, key=f"triage_btn_{idx}"):
                st.session_state.active_query = payload["search"]
                intent_info = understand_user_query(payload["search"], api_key)
                st.session_state.last_intent = intent_info
                st.session_state.search_results = asyncio.run(run_all_scrapers(intent_info, selected_vendors))
                st.rerun()
        idx += 1

# Execute search when button clicked
if run_search:
    if not query_input.strip():
        st.warning("Please enter a component or drone requirement.")
    elif pre_screen_intent and pre_screen_intent.get("is_extremely_general"):
        st.info("Please select one of the specific drone classes above so the agent only searches compatible specifications.")
    else:
        st.session_state.active_query = query_input.strip()
        with st.spinner(f"Verifying technical specs for '{query_input.strip()}' across {len(selected_vendors)} vendor databases..."):
            intent_info = understand_user_query(query_input.strip(), api_key)
            matched_items = asyncio.run(run_all_scrapers(intent_info, selected_vendors))
            st.session_state.last_intent = intent_info
            st.session_state.search_results = matched_items

# Display Advisor translation & Spec Locks
if st.session_state.last_intent and not st.session_state.last_intent.get("is_extremely_general"):
    intent = st.session_state.last_intent
    queries_badges = "".join([f'<span class="ai-badge">🔎 {q}</span>' for q in intent["search_queries"]])
    locks_html = ""
    if intent.get("locked_stators"):
        locks_html += f'<span class="lock-badge">🔒 Stator Lock: {", ".join(intent["locked_stators"])}</span>'
    if intent.get("locked_kvs"):
        locks_html += f'<span class="lock-badge">🔒 KV Lock: {", ".join([k + "KV" for k in intent["locked_kvs"]])}</span>'

    st.markdown(f"""
    <div class="ai-advisor-card">
        <div>🤖 <b>AI Technical Matcher:</b> {intent['ai_explanation']}</div>
        <div style="margin-top:6px; color:#475569;">
            <b>Identified Group:</b> <span class="ai-badge">{intent['category']}</span>
            {locks_html}
            <b>Parallel Scrapes Dispatched:</b> {queries_badges}
        </div>
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
        st.markdown('<div class="section-title">1. Product Search Findings (Low to High Rate Index)</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-note">Check the box for compatible parts, customize categorized tier labels below, and press <b>Add Selected Item(s) to BOQ</b>.</div>', unsafe_allow_html=True)

        st.markdown(f"""
        <div class="summary-strip">
            <div class="summary-pill">Stock Results Found: <b>{len(df_editor)}</b></div>
            <div class="summary-pill">Fulfilling Stores: <b>{active_store_count}</b></div>
            <div class="summary-pill">Target Entry Rate: <b>{lowest_str}</b></div>
        </div>
        """, unsafe_allow_html=True)

        edited_df = st.data_editor(
            df_editor,
            column_config={
                "Select": st.column_config.CheckboxColumn("Select", help="Add this specification", default=False, width="small"),
                "Product Name": st.column_config.TextColumn("Product Name", width="large", disabled=True),
                "Specification": st.column_config.TextColumn("Specification", width="medium", disabled=True),
                "Brand Name": st.column_config.TextColumn("Brand", width="small", disabled=True),
                "Vendor Name": st.column_config.TextColumn("Vendor", width="small", disabled=True),
                "SKU Name": st.column_config.TextColumn("SKU Name", width="small", disabled=True),
                "Rate (₹)": st.column_config.NumberColumn("Rate (₹)", format="₹%.2f", disabled=True),
                "Link": st.column_config.LinkColumn("Link", display_text="Source URL ↗", disabled=True),
            },
            use_container_width=True,
            hide_index=True,
            key="search_results_editor"
        )

        act_col1, act_col2 = st.columns([2.2, 3])
        default_cat = st.session_state.last_intent["category"] if st.session_state.last_intent else "Drone Part"
        with act_col1:
            custom_cat = st.text_input("Group/Category Tag for Selected Parts", value=default_cat)
        with act_col2:
            st.write("")
            st.write("")
            if st.button("➕ Add Selected Item(s) to BOQ", type="primary"):
                selected_rows = edited_df[edited_df["Select"] == True]
                if selected_rows.empty:
                    st.warning("Please toggle 'Select' checkboxes on compatible matches first.")
                else:
                    added = 0
                    for _, row in selected_rows.iterrows():
                        st.session_state.boq_cart.append({
                            "Category": custom_cat.strip() or default_cat,
                            "Item Name": row["Product Name"],
                            "Rate": float(row["Rate (₹)"]),
                            "Vendor": row["Vendor Name"],
                            "SKU": row["SKU Name"],
                            "Link": row["Link"],
                        })
                        added += 1
                    st.success(f"Added {added} item(s) to BOQ summary card below.")
                    st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)
elif st.session_state.last_intent is not None and not st.session_state.last_intent.get("is_extremely_general"):
    st.info("No exact in-stock component results match this locked specification across the selected stores.")

# ----------------- BILL OF QUANTITIES (BOQ) SUMMARY CARD -----------------
st.markdown('<div class="section-card">', unsafe_allow_html=True)
st.markdown('<div class="section-title">2. Build Bill of Quantities (BOQ) Summary Card</div>', unsafe_allow_html=True)
st.markdown('<div class="section-note">Add multi-tier specs across all sub-queries here. Edit pricing & tags inline, remove unneeded entries, and export to Excel (.xlsx).</div>', unsafe_allow_html=True)

if st.session_state.boq_cart:
    boq_df = pd.DataFrame(st.session_state.boq_cart)
    boq_df.insert(0, "Sr. No.", range(1, len(boq_df) + 1))
    boq_df["Remove"] = False

    total_cost = boq_df["Rate"].sum()

    st.markdown(f"""
    <div class="summary-strip">
        <div class="summary-pill">Total Bill Items: <b>{len(boq_df)}</b></div>
        <div class="summary-pill">Integrated Vendors: <b>{boq_df['Vendor'].nunique()}</b></div>
        <div class="summary-pill">Projected Build Cost: <b>₹{total_cost:,.2f}</b></div>
    </div>
    """, unsafe_allow_html=True)

    edited_boq = st.data_editor(
        boq_df,
        column_config={
            "Sr. No.": st.column_config.NumberColumn("Sr. No.", width="small", disabled=True),
            "Category": st.column_config.TextColumn("Group / Tier Category", width="medium"),
            "Item Name": st.column_config.TextColumn("Item / Component Specification", width="large"),
            "Rate": st.column_config.NumberColumn("Rate (₹)", format="₹%.2f"),
            "Vendor": st.column_config.TextColumn("Vendor", width="small", disabled=True),
            "SKU": st.column_config.TextColumn("SKU Reference", width="small", disabled=True),
            "Link": st.column_config.LinkColumn("View ↗", display_text="Source URL ↗", disabled=True),
            "Remove": st.column_config.CheckboxColumn("Remove", help="Omit this specification line", default=False, width="small"),
        },
        use_container_width=True, hide_index=True, key="boq_table_editor"
    )

    for idx in range(len(st.session_state.boq_cart)):
        st.session_state.boq_cart[idx]["Category"] = edited_boq.loc[idx, "Category"]
        st.session_state.boq_cart[idx]["Item Name"] = edited_boq.loc[idx, "Item Name"]
        st.session_state.boq_cart[idx]["Rate"] = float(edited_boq.loc[idx, "Rate"])

    export_df = edited_boq[["Sr. No.", "Category", "Item Name", "Rate", "Vendor", "SKU", "Link"]].copy()
    xlsx_out_bytes = dataframe_to_xlsx_bytes(export_df)

    b_col1, b_col2, b_col3 = st.columns([2, 1.5, 1.5])
    with b_col1:
        st.download_button(
            label="📥 Export BOQ to Excel (.xlsx)", data=xlsx_out_bytes, file_name="The_Drone_Builder_BOQ.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary", use_container_width=True
        )
    with b_col2:
        if st.button("🗑️ Remove Checked Specifications", type="secondary", use_container_width=True):
            keep_indices = edited_boq[edited_boq["Remove"] == False].index.tolist()
            st.session_state.boq_cart = [st.session_state.boq_cart[i] for i in keep_indices]
            st.rerun()
    with b_col3:
        if st.button("🧹 Clear Entire BOQ Summary Data", type="secondary", use_container_width=True):
            st.session_state.boq_cart = []
            st.rerun()
else:
    st.info("No items added yet. Search for motors, frames, or hardware specs above, tick checkboxes, and click 'Add Selected Item(s) to BOQ'.")

st.markdown('</div>', unsafe_allow_html=True)
