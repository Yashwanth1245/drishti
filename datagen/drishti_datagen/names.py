"""Karnataka-realistic person name factory.

Produces names matching the state's community mix (Census 2011: Hindu 84%,
Muslim 12.9%, Christian 1.9%) and regional conventions documented in
reference/demographics_names.json:
  - south / Old Mysuru: initials before the given name (B. Ravi Kumar)
  - north Karnataka: surname style (Basavaraj Patil)
  - coastal: community surnames (Shetty, Poojary, D'Souza ...)
The same factory serves police employees and (later stages) civilians, so all
names in the database share one consistent onomastic world.
"""

from .config import REGION_NORTH, REGION_COASTAL, RELIGION_MIX
from .util import weighted

INITIALS = list("ABCDGHKLMNPRSTVY")

# Surname groupings by style; drawn from the researched surname pool.
NORTH_SURNAMES = ["Patil", "Kulkarni", "Desai", "Biradar", "Hiremath", "Angadi",
                  "Badiger", "Kumbar", "Talwar", "Mane", "Jadhav", "Chavan",
                  "Math", "Joshi", "Deshpande"]
COASTAL_HINDU_SURNAMES = ["Shetty", "Rai", "Poojary", "Alva", "Salian", "Kotian",
                          "Suvarna", "Devadiga", "Bangera", "Amin", "Karkera",
                          "Shenoy", "Pai", "Kamath", "Prabhu", "Kini", "Bhat", "Hegde"]
SOUTH_SUFFIXES = ["Gowda", "Urs", "Reddy", "Naik", "Murthy", "Rao"]
CHRISTIAN_SURNAMES = ["D'Souza", "Fernandes", "Pinto", "Lobo", "Rodrigues",
                      "Pereira", "Mascarenhas", "Sequeira", "Menezes"]
MUSLIM_SURNAMES = ["Khan", "Sheikh", "Pasha", "Mulla", "Nadaf", "Bagwan", "Mujawar"]

# Compound-name building blocks for extra variety (very common in Karnataka).
COMPOUND_SECONDS = ["Kumar", "Prasad", "Raju", "Swamy", "Murthy", "Anand", "Kiran", "Babu"]
FEMALE_SUFFIXES = ["Bai", "Kumari", "Devi"]
NICKNAMES = ["Chikka", "Dodda", "Kariya", "Kempa", "Putta"]   # true-alias street names


class NameFactory:
    def __init__(self, ref_names: dict):
        n = ref_names
        self.male_hindu = n["maleHindu"]
        self.female_hindu = n["femaleHindu"]
        self.male_muslim = n["maleMuslim"]
        self.female_muslim = n["femaleMuslim"]
        self.christian = n["christian"]
        self.variants = {v["canonical"]: v["variants"] for v in n.get("variants", [])}

    def region(self, district: str) -> str:
        if district in REGION_NORTH:
            return "north"
        if district in REGION_COASTAL:
            return "coastal"
        return "south"

    def person(self, rng, district: str, gender: str | None = None,
               religion: str | None = None) -> dict:
        """Return dict(display, first, gender 'M'/'F', religion)."""
        gender = gender or ("M" if rng.random() < 0.5 else "F")
        religion = religion or weighted(rng, RELIGION_MIX)
        region = self.region(district)

        if religion == "Muslim":
            first = rng.choice(self.male_muslim if gender == "M" else self.female_muslim)
            if gender == "M" and region == "north" and rng.random() < 0.25:
                display = f"{first}sab"                      # rural north convention
            elif rng.random() < 0.55:
                display = f"{first} {rng.choice(MUSLIM_SURNAMES)}"
            else:
                second = rng.choice(self.male_muslim if gender == "M" else self.female_muslim)
                display = f"{first} {second}" if second != first else first
        elif religion == "Christian":
            first = rng.choice(self.christian)
            display = f"{first} {rng.choice(CHRISTIAN_SURNAMES)}"
        else:  # Hindu + Others share Kannada naming conventions
            first = rng.choice(self.male_hindu if gender == "M" else self.female_hindu)
            if gender == "M" and rng.random() < 0.28:
                first = f"{first} {rng.choice(COMPOUND_SECONDS)}"
            elif gender == "F" and rng.random() < 0.14:
                first = f"{first} {rng.choice(FEMALE_SUFFIXES)}"
            if region == "north":
                display = f"{first} {rng.choice(NORTH_SURNAMES)}"
            elif region == "coastal":
                display = f"{first} {rng.choice(COASTAL_HINDU_SURNAMES)}"
            else:  # south: initials style, occasional community suffix
                r = rng.random()
                if r < 0.45:
                    display = f"{rng.choice(INITIALS)}. {first}"
                elif r < 0.60:
                    display = f"{rng.choice(INITIALS)}. {rng.choice(INITIALS)}. {first}"
                elif r < 0.75:
                    display = f"{first} {rng.choice(SOUTH_SUFFIXES)}"
                else:
                    display = first
        return {"display": display, "first": first, "gender": gender, "religion": religion}

    def variant_of(self, display: str, rng) -> str:
        """Alternate official spelling of the SAME person's name.

        Models how one individual appears differently across FIRs: trailing-a
        toggles (Manjunath/Manjunatha), compound join (Ravi Kumar -> Ravikumar),
        initials moving or dropping (B. Ravi -> Ravi B. -> Ravi), and researched
        transliteration sets (Mohammed -> Mohammad / Md.).
        """
        tokens = display.split()
        ops = []

        for i, t in enumerate(tokens):
            if t.rstrip(".") in self.variants and len(self.variants[t.rstrip(".")]) > 0:
                ops.append(("known", i))
            if len(t) > 4 and t[0].isupper() and "." not in t:
                ops.append(("toggle_a", i))
        word_idx = [i for i, t in enumerate(tokens) if "." not in t]
        if len(word_idx) >= 2:
            ops.append(("join", word_idx[0]))
        initial_idx = [i for i, t in enumerate(tokens) if t.endswith(".") and len(t) <= 3]
        if initial_idx:
            ops.append(("move_initial", initial_idx[0]))
            ops.append(("drop_initial", initial_idx[0]))
        elif len(tokens) <= 2:
            ops.append(("add_initial", 0))

        if not ops:
            return f"{rng.choice(INITIALS)}. {display}"
        op, i = rng.choice(ops)
        t = list(tokens)
        if op == "known":
            t[i] = rng.choice(self.variants[t[i].rstrip(".")])
        elif op == "toggle_a":
            if t[i].endswith("a"):
                t[i] = t[i][:-1]                 # Manjunatha -> Manjunath
            elif t[i].endswith("u"):
                t[i] = t[i][:-1] + "a"           # Nagaraju -> Nagaraja
            else:
                t[i] = t[i] + "a"                # Manjunath -> Manjunatha
        elif op == "join":
            t[i] = t[i] + t[i + 1].lower()
            del t[i + 1]
        elif op == "move_initial":
            initial = t.pop(i)
            t.append(initial)
        elif op == "drop_initial":
            t.pop(i)
        elif op == "add_initial":
            t.insert(0, f"{rng.choice(INITIALS)}.")
        result = " ".join(t)
        return result if result != display else f"{rng.choice(INITIALS)}. {display}"
