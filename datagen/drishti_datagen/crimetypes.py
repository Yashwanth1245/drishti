"""The crime-type catalog: every offence the generator produces, fully specified.

Each entry carries its calibrated share of annual cases (NCRB CII-2023 Karnataka,
see reference/crime_calibration.json), legal mapping keyword (resolved against
the offence registry / special acts), timing signature, place profile, party
profile, property profile, MO vocabulary and narrative templates. The case
engine is generic — ALL offence-specific behavior lives in this table so the
calibration is auditable in one file.

Field defaults (see D()): weight, kw/sll, gravity 2, unknown accused 0.05,
n_accused [(1,.7),(2,.3)], victim 'self', hours uniform, months flat, delay
short, places street, bengaluru share None (population-weighted), station pref
'regular', property None, mo [], templates [].
"""


def D(**kw):
    base = dict(
        weight=0.01, kw=None, sll=None, gravity=2, unknown=0.05,
        n_accused=[(1, .7), (2, .3)], victim="self",
        hours=[((6, 22), 1.0)], months={}, delay=[(0, .5), (1, .3), (3, .2)],
        places=[("Street/Road", .6), ("House/Residence", .4)],
        bshare=None, station="regular", prop=None, mo=[], templates=[],
        female_victim=False, year_mult=None,
    )
    base.update(kw)
    return base


FESTIVAL = {10: 1.35, 11: 1.30, 9: 1.10}       # Dasara–Deepavali property bump
SUMMER_TRAVEL = {4: 1.15, 5: 1.15}

CRIME_TYPES = {
    # ------------------------------------------------------ body offences ----
    "murder": D(weight=.006, kw="Murder", gravity=1, unknown=.08,
        n_accused=[(1, .5), (2, .25), (3, .15), (4, .10)], victim="other",
        hours=[((19, 24), .4), ((0, 5), .2), ((5, 19), .4)],
        delay=[(0, .85), (1, .15)],
        places=[("House/Residence", .4), ("Street/Road", .3), ("Farm/Field", .3)],
        mo=["assault-deadly-weapon", "old-enmity", "drunken-brawl", "property-dispute"],
        templates=["{comp}, {crel} of the deceased, reported that on {date} at about "
                   "{time} hrs near {place}, the accused {acc} assaulted {vict} with "
                   "{weapon} over {motive}, causing death on the spot. {mo_s}"]),
    "attempt_murder": D(weight=.014, kw="Attempt to murder", gravity=1, unknown=.10,
        n_accused=[(1, .5), (2, .3), (3, .2)], victim="other",
        hours=[((18, 24), .45), ((6, 18), .55)], delay=[(0, .8), (1, .2)],
        mo=["assault-deadly-weapon", "old-enmity", "gang-rivalry"],
        templates=["On {date} at about {time} hrs near {place}, the accused {acc} "
                   "attacked {vict} with {weapon} with intent to kill over {motive}. "
                   "The injured has been shifted to hospital. {mo_s}"]),
    "hurt": D(weight=.14, kw="Grievous hurt", unknown=.06,
        n_accused=[(1, .55), (2, .3), (3, .15)], victim="other",
        delay=[(0, .7), (1, .2), (2, .1)],
        mo=["simple-assault", "neighbour-dispute", "road-rage", "drunken-brawl"],
        templates=["{comp} reported that on {date} at about {time} hrs at {place}, "
                   "the accused {acc} picked a quarrel over {motive} and assaulted "
                   "{vict}, causing injuries. {mo_s}"]),
    "kidnapping": D(weight=.017, kw="Kidnapping", gravity=1, unknown=.30,
        victim="other", delay=[(0, .5), (1, .3), (3, .2)],
        mo=["minor-missing", "love-affair-elopement", "ransom-demand"],
        templates=["{comp} reported that {vict} has been missing from {place} since "
                   "{date} {time} hrs and is suspected to have been kidnapped. {mo_s}"]),
    "rape": D(weight=.003, kw="Rape", gravity=1, unknown=.05, victim="other",
        female_victim=True, station="women",
        delay=[(1, .3), (7, .3), (30, .25), (120, .15)],
        mo=["known-person-offender", "false-promise-marriage"],
        templates=["The victim reported that the accused {acc}, known to her, "
                   "committed sexual assault at {place} on {date}. Medical "
                   "examination arranged; statement recorded. {mo_s}"]),
    "molestation": D(weight=.020, kw="Assault on woman", unknown=.15, victim="other",
        female_victim=True, station="women",
        delay=[(0, .4), (1, .3), (7, .3)],
        mo=["workplace-harassment", "stalking", "public-place-harassment"],
        templates=["The complainant reported that on {date} at about {time} hrs at "
                   "{place}, the accused {acc} outraged her modesty. {mo_s}"]),
    "cruelty_498a": D(weight=.014, kw="Cruelty", unknown=.0, victim="other",
        female_victim=True, station="women",
        n_accused=[(1, .3), (2, .35), (3, .35)],
        delay=[(30, .4), (120, .35), (365, .25)],
        places=[("House/Residence", 1.0)],
        mo=["dowry-harassment", "domestic-violence"],
        templates=["The complainant stated that her husband {acc} and in-laws "
                   "subjected her to mental and physical cruelty demanding "
                   "additional dowry since {date}. {mo_s}"]),
    "dowry_death": D(weight=.0008, kw="Dowry death", gravity=1, unknown=.0,
        victim="other", female_victim=True,
        n_accused=[(2, .4), (3, .6)], places=[("House/Residence", 1.0)],
        mo=["dowry-harassment"],
        templates=["{comp} reported that his daughter {vict} died under unnatural "
                   "circumstances at her matrimonial home at {place} on {date}; "
                   "dowry harassment by {acc} is alleged. {mo_s}"]),
    "rioting": D(weight=.019, kw="Rioting", unknown=.20,
        n_accused=[(4, .3), (6, .4), (8, .3)], victim="other",
        mo=["land-dispute-group-clash", "group-clash", "protest-violence"],
        templates=["On {date} at about {time} hrs at {place}, the accused {acc} "
                   "formed an unlawful assembly armed with sticks and stones and "
                   "rioted over {motive}, damaging property. {mo_s}"]),
    # -------------------------------------------------- property offences ----
    "theft": D(weight=.054, kw="Theft", unknown=.55,
        months=FESTIVAL, delay=[(0, .5), (1, .35), (3, .15)],
        places=[("House/Residence", .3), ("Shop/Commercial", .25),
                ("Street/Road", .25), ("Public Transport", .2)],
        prop=("mixed", .30), mo=["mobile-lifting", "shop-theft", "servant-theft",
                                 "luggage-lifting"],
        templates=["{comp} reported theft of {prop} at {place} on {date} between "
                   "{time} and {time2} hrs by {acc}. {mo_s}"]),
    "vehicle_theft": D(weight=.062, kw="Theft", unknown=.62, bshare=.442,
        months=FESTIVAL, delay=[(0, .55), (1, .35), (2, .10)],
        places=[("Street/Road", .55), ("House/Residence", .30), ("Public Transport", .15)],
        prop=("vehicle", .28), mo=["two-wheeler-lifting", "duplicate-key",
                                   "parking-lot-theft"],
        templates=["{comp} reported that his/her {prop} parked at {place} was "
                   "stolen on {date} between {time} and {time2} hrs by {acc}. {mo_s}"]),
    "snatching": D(weight=.012, kw="Snatching", unknown=.45, bshare=.35,
        months={8: 1.15, 9: 1.2, 10: 1.35, 11: 1.3},
        hours=[((5, 8), .45), ((18, 22), .40), ((8, 18), .15)],
        delay=[(0, .9), (1, .1)],
        places=[("Street/Road", .8), ("Park/Ground", .2)],
        prop=("gold", .22), victim="self", female_victim=True,
        mo=["two-wheeler-pillion-snatch", "morning-walk-target", "gold-chain-snatch"],
        templates=["{comp} reported that on {date} at about {time} hrs while walking "
                   "near {place}, two persons on a motorcycle snatched her gold "
                   "chain ({prop}) and sped away. {mo_s}"]),
    "robbery": D(weight=.008, kw="Robbery", gravity=1, unknown=.40,
        hours=[((19, 24), .5), ((0, 4), .2), ((4, 19), .3)],
        n_accused=[(2, .5), (3, .5)], prop=("mixed", .30),
        mo=["knife-point-robbery", "highway-waylay"],
        templates=["On {date} at about {time} hrs near {place}, the accused {acc} "
                   "waylaid {vict} at knife point and robbed {prop}. {mo_s}"]),
    "dacoity": D(weight=.0004, kw="Dacoity", gravity=1, unknown=.35,
        n_accused=[(5, .6), (6, .4)], prop=("mixed", .40),
        hours=[((22, 24), .5), ((0, 4), .5)],
        mo=["armed-gang-dacoity", "highway-waylay"],
        templates=["A gang of {nacc} armed persons {acc} committed dacoity at {place} "
                   "on the night of {date}, decamping with {prop}. {mo_s}"]),
    "burglary": D(weight=.028, kw="burglary", unknown=.58,
        months={**FESTIVAL, **SUMMER_TRAVEL},
        hours=[((23, 24), .35), ((0, 4), .45), ((10, 17), .20)],  # NCRB: 80.5% night
        delay=[(0, .7), (1, .3)],
        places=[("House/Residence", .8), ("Shop/Commercial", .2)],
        prop=("mixed", .32), mo=["lock-break-entry", "gas-cutter-entry",
                                 "roof-entry", "locked-house-target"],
        templates=["{comp} reported that between {time} hrs on {date} and the next "
                   "morning, unknown persons committed house-breaking at {place} by "
                   "{mo_phrase} and committed theft of {prop}. {mo_s}"]),
    "cheating": D(weight=.029, kw="Cheating", unknown=.25,
        delay=[(7, .3), (15, .3), (45, .25), (120, .15)],
        places=[("Shop/Commercial", .4), ("House/Residence", .3), ("Bank", .3)],
        prop=("cash", .18), mo=["fake-investment-scheme", "job-fraud",
                                "land-document-fraud", "chit-fund-fraud"],
        templates=["{comp} reported that the accused {acc} induced him/her to part "
                   "with Rs. {value} on the pretext of {mo_phrase} and cheated "
                   "him/her. {mo_s}"]),
    "forgery": D(weight=.006, kw="Forgery", unknown=.15,
        delay=[(30, .5), (120, .5)],
        places=[("Bank", .4), ("Shop/Commercial", .3), ("House/Residence", .3)],
        mo=["forged-land-records", "forged-cheque", "fake-documents"],
        templates=["{comp} reported that the accused {acc} forged {mo_phrase} and "
                   "used them as genuine to derive wrongful gain. {mo_s}"]),
    "cyber_fraud": D(weight=.102, sll=[("IT Act", "66D"), ("IT Act", "66C")],
        kw="Cheating", unknown=.72, bshare=.805, station="cen",
        hours=[((9, 21), 1.0)], delay=[(1, .3), (3, .3), (10, .25), (30, .15)],
        places=[("Online/Cyberspace", 1.0)], prop=("cash", .06),
        year_mult={2021: .55, 2022: .75, 2023: 1.0, 2024: 1.15, 2025: 1.4, 2026: 1.65},
        mo=["otp-fraud", "investment-app-fraud", "digital-arrest-scam", "kyc-fraud",
            "olx-marketplace-fraud", "loan-app-extortion"],
        templates=["{comp} reported that unknown fraudsters contacted him/her by "
                   "phone/online and by {mo_phrase} induced transfer of Rs. {value} "
                   "to unknown bank accounts. NCRP complaint number cited. {mo_s}"]),
    "mischief": D(weight=.025, kw="Mischief", unknown=.35,
        mo=["property-damage", "vehicle-vandalism"],
        templates=["{comp} reported that on {date} at about {time} hrs, the accused "
                   "{acc} committed mischief at {place} causing damage of about "
                   "Rs. {value}. {mo_s}"]),
    "trespass": D(weight=.012, kw="trespass", unknown=.10,
        places=[("House/Residence", .7), ("Farm/Field", .3)],
        mo=["land-dispute", "neighbour-dispute"],
        templates=["{comp} reported that the accused {acc} criminally trespassed "
                   "into his/her property at {place} on {date} over {motive}. {mo_s}"]),
    "intimidation": D(weight=.030, kw="intimidation", unknown=.08,
        mo=["threat-over-dispute", "extortion-threat"],
        templates=["{comp} reported that the accused {acc} criminally intimidated "
                   "him/her at {place} on {date}, threatening dire consequences "
                   "over {motive}. {mo_s}"]),
    # -------------------------------------------------------- road / misc ----
    "road_304a": D(weight=.054, kw="negligence", unknown=.12, station="traffic",
        hours=[((6, 11), .25), ((17, 23), .45), ((23, 24), .15), ((0, 6), .15)],
        places=[("Highway", .5), ("Street/Road", .5)], victim="other",
        mo=["hit-and-run", "over-speeding", "drunken-driving"],
        templates=["On {date} at about {time} hrs on {place}, the vehicle driven by "
                   "{acc} in a rash and negligent manner knocked down {vict}, who "
                   "succumbed to injuries. {mo_s}"]),
    "rash_driving": D(weight=.080, kw="Rash driving", unknown=.10, station="traffic",
        places=[("Highway", .5), ("Street/Road", .5)],
        mo=["over-speeding", "wrong-side-driving", "drunken-driving"],
        templates=["On {date} at about {time} hrs, the accused {acc} drove his "
                   "vehicle in a rash and negligent manner on {place} endangering "
                   "public safety, causing injuries to {vict}. {mo_s}"]),
    # -------------------------------------------------------------- SLL ------
    "ndps": D(weight=.032, sll=[("NDPS Act", "20(b)"), ("NDPS Act", "21"),
                                ("NDPS Act", "22")],
        gravity=1, unknown=.0, bshare=.509, station="cen",
        n_accused=[(1, .55), (2, .3), (3, .15)], victim="state",
        mo=["ganja-peddling", "synthetic-drug-possession", "interstate-transport"],
        templates=["On credible information, the police intercepted the accused "
                   "{acc} near {place} on {date} and seized {qty} of contraband "
                   "({mo_phrase}). Accused arrested under the NDPS Act. {mo_s}"]),
    "gambling": D(weight=.064, sll=[("Karnataka Police Act", "78"),
                                    ("Karnataka Police Act", "87")],
        unknown=.0, bshare=.046, victim="state",
        n_accused=[(3, .3), (4, .3), (5, .2), (6, .2)],
        mo=["matka-gambling", "card-den", "online-betting"],
        templates=["On {date} at about {time} hrs, on credible information, the "
                   "police raided premises at {place} and apprehended the accused "
                   "{acc} engaged in {mo_phrase}; cash of Rs. {value} seized. {mo_s}"]),
    "excise": D(weight=.044, sll=[("Karnataka Excise Act", "32"),
                                  ("Karnataka Excise Act", "38A")],
        unknown=.0, victim="state",
        mo=["illicit-liquor-sale", "unlicensed-transport"],
        templates=["On {date}, the police raided {place} and found the accused {acc} "
                   "engaged in {mo_phrase}; liquor worth Rs. {value} seized. {mo_s}"]),
    # -------------------------------------------------------------- UDR ------
    "udr": D(weight=.060, kw="__udr__", unknown=1.0, victim="other",
        delay=[(0, .9), (1, .1)],
        places=[("House/Residence", .35), ("Lake/Water Body", .25),
                ("Farm/Field", .2), ("Railway Station", .2)],
        mo=["suspected-suicide", "accidental-drowning", "unidentified-body"],
        templates=["{comp} reported that {vict} was found dead at {place} on {date}. "
                   "No visible injuries; cause of death to be ascertained. UDR "
                   "registered; inquest conducted. {mo_s}"]),
}

WEAPONS = ["a machete (longu)", "a club", "an iron rod", "a knife", "a sickle"]
MOTIVES = ["a land dispute", "an old enmity", "a money dispute",
           "a family dispute", "a trivial quarrel", "political rivalry"]
KANNADA_LINES = [
    "Sthala panchanama maadalagide.",
    "Doorudarara helike dakhalisalagide.",
    "ಆರೋಪಿ ಪತ್ತೆಗಾಗಿ ತನಿಖೆ ಮುಂದುವರಿದಿದೆ.",
    "ಪ್ರಕರಣ ದಾಖಲಿಸಿ ತನಿಖೆ ಕೈಗೊಳ್ಳಲಾಗಿದೆ.",
]
TERSE = ["Case registered. Investigation taken up.",
         "Complaint received; FIR registered. IO deputed to spot."]
