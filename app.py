"""My Festival REST API — M10 starter (CSC Rahti).

FI: Tämä on M10-tehtävän lähtöpohja. GET /api/artists on valmiina mallina;
    toteuta loput TODO-kohdat. Aja paikallisesti:  python app.py
    ja testaa:  python test_endpoints.py http://localhost:8080
EN: This is the M10 starter. GET /api/artists is done as an example;
    implement the remaining TODOs. Run locally:  python app.py
    and test:  python test_endpoints.py http://localhost:8080
"""
import os
import sqlite3
import datetime
from flask import Flask, jsonify, request

app = Flask(__name__)

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "myfestival.db"))

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn

# Alustetaan tietokanta, jos testiskripti ei sitä tee
def init_db_if_needed():
    conn = get_db()
    try:
        # Luodaan taulut, jos niitä ei ole
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS Artist (artist_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, country TEXT);
            CREATE TABLE IF NOT EXISTS Stage (stage_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS Day (day_id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL UNIQUE);
            CREATE TABLE IF NOT EXISTS EventType (event_type_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE);
            CREATE TABLE IF NOT EXISTS Event (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT, start_dt TEXT,
                artist_id INTEGER, stage_id INTEGER, event_type_id INTEGER,
                FOREIGN KEY (artist_id) REFERENCES Artist(artist_id),
                FOREIGN KEY (stage_id) REFERENCES Stage(stage_id)
            );
        """)
        # Lisätään perusdata, jos se puuttuu
        if not conn.execute("SELECT 1 FROM Stage LIMIT 1").fetchone():
            conn.execute("INSERT INTO Stage (name) VALUES ('Main Stage'), ('Club Stage')")
            conn.execute("INSERT INTO Day (date) VALUES ('2025-07-04'), ('2025-07-05')")
            conn.execute("INSERT INTO Artist (name) VALUES ('Test Artist')")
            conn.commit()
    except Exception as e:
        print(f"Init error: {e}")
    finally:
        conn.close()

init_db_if_needed()

@app.get("/")
def health():
    return jsonify(status="ok")

@app.get("/api/artists")
def get_artists():
    conn = get_db()
    rows = conn.execute("SELECT artist_id, name, country FROM Artist ORDER BY name").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.get("/api/days")
def get_days():
    conn = get_db()
    rows = conn.execute("SELECT day_id, date FROM Day ORDER BY date").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.get("/api/stages")
def get_stages():
    conn = get_db()
    rows = conn.execute("SELECT stage_id, name FROM Stage ORDER BY stage_id").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.get("/api/artists/<int:artist_id>/events")
def get_artist_events(artist_id):
    conn = get_db()
    if not conn.execute("SELECT 1 FROM Artist WHERE artist_id = ?", (artist_id,)).fetchone():
        conn.close()
        return jsonify(error="Artist not found"), 404

    sql = """
        SELECT e.event_id, substr(e.start_dt, 1, 10) AS day, s.name AS stage, e.start_dt AS starts
        FROM Event e
        LEFT JOIN Stage s ON e.stage_id = s.stage_id
        WHERE e.artist_id = ?
        ORDER BY e.start_dt ASC
    """
    rows = conn.execute(sql, (artist_id,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.get("/api/timetable")
def get_timetable():
    day = request.args.get("day")
    conn = get_db()
    
    # KORJAUS 1: Korvattu e.end_dt NULL-arvolla, koska sarake ei ole tietokannassa (estää 500-virheen)
    sql = """
        SELECT e.start_dt AS starts, 
               NULL AS ends, 
               substr(e.start_dt, 1, 10) AS date, 
               s.name AS stage, 
               a.name AS artist
        FROM Event e
        LEFT JOIN Stage s ON e.stage_id = s.stage_id
        LEFT JOIN Artist a ON e.artist_id = a.artist_id
    """
    params = []
    if day:
        try:
            datetime.datetime.strptime(day, "%Y-%m-%d")
        except ValueError:
            conn.close()
            return jsonify(error="Invalid date format"), 400
        sql += " WHERE e.start_dt LIKE ?"
        params.append(f"{day}%")
    
    sql += " ORDER BY e.start_dt ASC"
    rows = conn.execute(sql, tuple(params)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.post("/api/events")
def create_event():
    body = request.get_json(silent=True) or {}
    required = ["artist_id", "stage_id", "day_id", "start_dt"]
    if not all(k in body for k in required):
        return jsonify(error="Missing fields"), 400

    conn = get_db()
    try:
        day_row = conn.execute("SELECT date FROM Day WHERE day_id = ?", (body["day_id"],)).fetchone()
        if not day_row:
            return jsonify(error="Invalid day_id"), 400
        
        start_str = str(body["start_dt"])
        full_start = f"{day_row['date']} {start_str}" if len(start_str) <= 5 else start_str
        
        # KORJAUS 2: Käsitellään sekä HH:MM että HH:MM:SS muodot (estää 'unconverted data' virheen)
        try:
            st = datetime.datetime.strptime(full_start, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            st = datetime.datetime.strptime(full_start, "%Y-%m-%d %H:%M")

        with conn:
            et = conn.execute("SELECT event_type_id FROM EventType WHERE name = 'performance'").fetchone()
            if et:
                et_id = et['event_type_id']
            else:
                et_id = conn.execute("INSERT INTO EventType (name) VALUES ('performance')").lastrowid

            # KORJAUS 3: Poistettu end_dt INSERT-lauseesta
            cur = conn.execute(
                "INSERT INTO Event (title, start_dt, artist_id, stage_id, event_type_id) VALUES (?, ?, ?, ?, ?)",
                ("Performance", full_start, body["artist_id"], body["stage_id"], et_id)
            )
            ev_id = cur.lastrowid

        new_row = conn.execute("SELECT * FROM Event WHERE event_id = ?", (ev_id,)).fetchone()
        conn.close()
        return jsonify(dict(new_row)), 201
    except sqlite3.IntegrityError as e:
        conn.close()
        return jsonify(error=str(e)), 400
    except Exception as e:
        conn.close()
        return jsonify(error=str(e)), 400

@app.delete("/api/events/<int:event_id>")
def delete_event(event_id):
    conn = get_db()
    with conn:
        cur = conn.execute("DELETE FROM Event WHERE event_id = ?", (event_id,))
    conn.close()
    if cur.rowcount == 0:
        return jsonify(error="Not found"), 404
    return "", 204

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=True)