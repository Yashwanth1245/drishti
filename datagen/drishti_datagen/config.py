"""Every tunable constant of the generator, with its source.

Nothing in the pipeline may hardcode a rate, count, or coordinate — it must live
here so a reviewer can audit every assumption in one file. Constants derived from
research carry their source; heuristics say so explicitly.
"""

from pathlib import Path

PKG_DIR = Path(__file__).parent
ROOT = PKG_DIR.parent.parent               # repository root
REFERENCE_DIR = ROOT / "reference"
EXPORT_DIR = ROOT / "exports"
DB_PATH = EXPORT_DIR / "drishti.db"

DEFAULT_SEED = 2026
DEFAULT_CASES = 200_000
SPAN_START = "2021-01-01"                  # 5.5 years of history
SPAN_END = "2026-06-30"
BNS_CUTOVER = "2024-07-01"                 # substantive law follows OFFENCE date (MHA notification)

# ---------------------------------------------------------------- geography --
# Approximate district HQ coordinates (public knowledge, +/-0.02 deg). Stations
# anchor to these with taluk-level offsets; good enough for district/station
# level mapping in a prototype. Upgrade path: real taluk gazetteer coords.
DISTRICT_HQ_COORDS = {
    "Bagalkote": (16.18, 75.70), "Ballari": (15.15, 76.93), "Belagavi": (15.85, 74.50),
    "Bengaluru Urban": (12.97, 77.59), "Bengaluru Rural": (13.20, 77.60),
    "Bengaluru South": (12.72, 77.28), "Bidar": (17.91, 77.52),
    "Chamarajanagara": (11.92, 76.94), "Chikkaballapura": (13.43, 77.73),
    "Chikkamagaluru": (13.32, 75.77), "Chitradurga": (14.23, 76.40),
    "Dakshina Kannada": (12.87, 74.84), "Davanagere": (14.47, 75.92),
    "Dharwad": (15.46, 75.01), "Gadag": (15.43, 75.63), "Hassan": (13.01, 76.10),
    "Haveri": (14.79, 75.40), "Kalaburagi": (17.33, 76.83), "Kodagu": (12.42, 75.74),
    "Kolar": (13.14, 78.13), "Koppal": (15.35, 76.15), "Mandya": (12.52, 76.90),
    "Mysuru": (12.30, 76.65), "Raichur": (16.21, 77.36), "Shivamogga": (13.93, 75.57),
    "Tumakuru": (13.34, 77.10), "Udupi": (13.34, 74.75), "Uttara Kannada": (14.81, 74.13),
    "Vijayanagara": (15.27, 76.39), "Vijayapura": (16.83, 75.71), "Yadgir": (16.77, 77.14),
}

# Station allocation. Commissionerate counts approximate the real law&order+
# traffic station counts; district counts are population-driven (heuristic tuned
# so the state total lands near the real ~1,100).
BENGALURU_CITY_STATIONS = 110
COMMISSIONERATE_STATIONS = {
    "Mysuru City Police": 22, "Hubballi-Dharwad City Police": 21,
    "Mangaluru City Police": 16, "Belagavi City Police": 12,
    "Kalaburagi City Police": 12,
}
COMMISSIONERATE_DISTRICT = {   # commissionerate -> revenue district it sits in
    "Bengaluru City Police": "Bengaluru Urban", "Mysuru City Police": "Mysuru",
    "Hubballi-Dharwad City Police": "Dharwad", "Mangaluru City Police": "Dakshina Kannada",
    "Belagavi City Police": "Belagavi", "Kalaburagi City Police": "Kalaburagi",
}
POP_PER_STATION = 52_000          # heuristic: rural station per ~52k residents
MIN_DISTRICT_STATIONS = 12
MAX_DISTRICT_STATIONS = 50
BENGALURU_URBAN_DISTRICT_STATIONS = 8   # small rural fringe outside city police

# Real Bengaluru City police station names (compiled from public BCP lists;
# supplements the 25 researched names to reach the ~110 real count).
BENGALURU_CITY_EXTRA_STATIONS = [
    "Ashok Nagar PS", "Adugodi PS", "Amruthahalli PS", "Annapoorneshwari Nagar PS",
    "Banaswadi PS", "Bagalagunte PS", "Byatarayanapura PS", "Byadarahalli PS",
    "Bharathi Nagar PS", "Bellandur PS", "Chandra Layout PS", "Chickpet PS",
    "City Market PS", "Cottonpet PS", "C.V. Raman Nagar PS", "Devarajeevanahalli PS",
    "Frazer Town PS", "Girinagar PS", "Govindapura PS", "Hanumanthanagar PS",
    "Hulimavu PS", "HAL PS", "Hennur PS", "Horamavu PS", "Hosakerehalli PS",
    "High Grounds PS", "Jalahalli PS", "J.P. Nagar PS", "Jeevan Bima Nagar PS",
    "Jnanabharathi PS", "Kadugodi PS", "Kamakshipalya PS", "K.G. Halli PS",
    "Konanakunte PS", "Kothanur PS", "Kumaraswamy Layout PS", "Laggere PS",
    "Lingarajapuram PS", "Magadi Road PS", "Mahalakshmi Layout PS", "Mahadevapura PS",
    "Marathahalli PS", "Mico Layout PS", "Nandini Layout PS", "Nagarabhavi PS",
    "Peenya PS", "Pulakeshinagar PS", "Rajagopalanagar PS", "Ramamurthy Nagar PS",
    "R.T. Nagar PS", "Sadashivanagar PS", "Sampigehalli PS", "Sanjaynagar PS",
    "Seshadripuram PS", "Srirampura PS", "Subramanyanagar PS", "Subramanyapura PS",
    "Suddaguntepalya PS", "Thalaghattapura PS", "Tilak Nagar PS", "Varthur PS",
    "Vyalikaval PS", "Vijayanagar PS", "Viveknagar PS", "Yelahanka New Town PS",
    "Sarjapur PS", "Bandepalya PS", "Parappana Agrahara PS", "Hulsur Gate PS",
    "Kalasipalya PS", "Siddapura PS", "Ashoknagar Traffic PS", "Kengeri Gate PS",
    "Soladevanahalli PS", "Chikkajala PS", "Vidyaranyapura PS", "Kodigehalli PS",
    "Gangammagudi PS", "Bagalur PS", "Avalahalli PS", "Anekal PS", "Attibele PS",
    "Suryanagar PS", "Hebbagodi PS", "Chandapura PS",
]

# ------------------------------------------------------------- demographics --
# Census 2011 Karnataka religion mix (reference/demographics_names.json notes).
RELIGION_MIX = [("Hindu", 0.840), ("Muslim", 0.129), ("Christian", 0.019), ("Others", 0.012)]

# Naming style regions (see reference notes on Karnataka onomastics).
REGION_NORTH = {
    "Bagalkote", "Belagavi", "Vijayapura", "Dharwad", "Gadag", "Haveri", "Bidar",
    "Kalaburagi", "Yadgir", "Raichur", "Koppal", "Ballari", "Vijayanagara",
}
REGION_COASTAL = {"Dakshina Kannada", "Udupi", "Uttara Kannada"}
# Everything else uses the Old-Mysuru initials convention.

# --------------------------------------------------------------- employees ---
# Station staffing composition (heuristic, roughly realistic sanctioned mix).
STATION_STAFF = [("PI", 1), ("PSI", 2), ("ASI", 2), ("HC", 3), ("PC", 4)]
SMALL_STATION_STAFF = [("PSI", 1), ("ASI", 2), ("HC", 2), ("PC", 3)]
EMPLOYEE_FEMALE_RATE = 0.10        # ~10% women in force; Women PS mostly women
BLOOD_GROUPS = [("O+", .37), ("B+", .32), ("A+", .22), ("AB+", .06),
                ("O-", .015), ("B-", .01), ("A-", .01), ("AB-", .005)]
