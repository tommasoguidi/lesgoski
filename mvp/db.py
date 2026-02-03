import sqlite3
from datetime import datetime
from modules import Trip
from config import DB_NAME, THRESHOLD_PRICE


def init():
    conn = sqlite3.connect(DB_NAME)
    # Creiamo una tabella che rispecchia la tua struttura, più l'ID e il timestamp di aggiornamento
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trips (
            id TEXT PRIMARY KEY,
            origin TEXT,
            destination TEXT,
            destination_full TEXT,
            out_departure_time DATETIME,
            out_arrival_time DATETIME,
            in_departure_time DATETIME,
            in_arrival_time DATETIME,
            out_price REAL,
            in_price REAL,
            total_price REAL,
            currency TEXT,
            last_seen DATETIME,
            notified BOOLEAN
        )
    """)
    conn.commit()
    conn.close()

def should_notify(trip: Trip) -> bool:
    """
    Ritorna True se:
    1. Il totale a/r è sotto una soglia
    Aggiorna il DB in entrambi i casi.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("SELECT total_price FROM trips WHERE id = ?", (trip.id,))
    row = cursor.fetchone()
    
    notify = False
    now = datetime.now()
    
    if row is None:
        # NUOVO VOLO
        cursor.execute("""
            INSERT INTO trips VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trip.id,
            trip.outbound.origin,
            trip.outbound.destination,
            trip.outbound.destinationFull,
            trip.outbound.departureTime,
            trip.outbound.arrivalTime,
            trip.inbound.departureTime,
            trip.inbound.arrivalTime,
            trip.outbound.price,
            trip.inbound.price,
            trip.totalPrice,
            trip.outbound.currency,
            now,
            False
        ))
    else:
        # se il volo era già registrato, aggiorniamo solo ciò che può essere cambiato
        # ossia soltanto i prezzi dato che l'identificativo univoco è basato su orari e numeri di volo
        # anche se cambiano l'orario di un volo che avevamo già registrato, lo consideriamo un volo "diverso"
        cursor.execute("""
            UPDATE trips SET total_price = ?, out_price = ?, in_price = ?, last_seen = ?, notified ? WHERE id = ?
        """, (trip.totalPrice, trip.outbound.price, trip.inbound.price, now, False, trip.id)
        )
    
    if trip.totalPrice <= THRESHOLD_PRICE:
        notify = True

    conn.commit()
    conn.close()
    return notify

def just_notified(trip: Trip):
    """Segna il viaggio come notificato nel DB"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE trips SET notified = ? WHERE id = ?", (True, trip.id))
    conn.commit()
    conn.close()

def prune_old_trips():
    """Cancella dal DB i viaggi il cui ritorno è già passato"""
    conn = sqlite3.connect(DB_NAME)
    now = datetime.now()
    count = conn.execute("DELETE FROM trips WHERE in_date < ?", (now,)).rowcount
    conn.commit()
    conn.close()
    if count > 0:
        print(f"🧹 Pulizia: rimossi {count} voli scaduti dal DB.")
