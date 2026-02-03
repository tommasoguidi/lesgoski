import os
from typing import List, Dict, Tuple
from dotenv import load_dotenv

# Carica le variabili dal file .env se esiste
load_dotenv()

# --- CONFIGURAZIONE BASE ---
# Usa os.getenv per leggere, con un valore di default se manca
NTFY_TOPIC = os.getenv("NTFY_TOPIC")
DEBUG = os.getenv("DEBUG", "False").lower() == "true"

# --- COSTANTI DI BUSINESS (Hardcoded o derivate) ---
# Queste ha senso lasciarle qui perché sono logica del programma
ORIGIN_IATA: List[str] = ['PSA']
CURRENCY: str = "EUR"
WEEKS_HORIZON: int = 8
THRESHOLD_PRICE: float = 70.0  # Soglia di notifica

# Orari standard per le strategie (venerdì sera, etc.)
# Tenerli qui evita di avere stringhe magiche sparse in scanner.py
BASE_DAY: int = 4  # 0=Mon, 1=Tue, ..., 4=Fri

STRATEGIES: List[str] = [
    "Fri-Sun",
    "Sat-Sun",
    "Sat-Mon"
]

TIME_RANGES: Dict[str, Tuple[str]] = {
    "FRI_EVENING": ("17:00", "23:59"),
    "SAT_MORNING": ("05:00", "12:00"),
    "SUN_EVENING": ("15:00", "23:59"),
    "MON_MORNING": ("05:00", "12:00")
}

LABELS_TO_TIME_RANGES: Dict[str, Tuple[Dict]] = {
    "Fri-Sun": (TIME_RANGES["FRI_EVENING"], TIME_RANGES["SUN_EVENING"]),
    "Sat-Sun": (TIME_RANGES["SAT_MORNING"], TIME_RANGES["SUN_EVENING"]),
    "Sat-Mon": (TIME_RANGES["SAT_MORNING"], TIME_RANGES["MON_MORNING"]),
}

LABELS_TO_OFFSETS: Dict[str, Tuple[int]] = {
    "Fri-Sun": (0, 2),
    "Sat-Sun": (1, 2),
    "Sat-Mon": (1, 3),
}
