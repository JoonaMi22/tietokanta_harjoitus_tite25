import sqlite3
from sqlite3 import Error
from pathlib import Path
from typing import Optional, Iterable, Tuple

DB_FILE = "myfestival.db"       # CLI project target: YOUR OWN My Festival database
# For exploring the shared FestivalDB instead, set DB_FILE = "festival.db"
SQL_INIT_FILE = "sql_festival_create.sql"  # (re)creates the shared FestivalDB v2 — not your My Festival db

# =====================================================================
# ---------------------------- Utility --------------------------------
# =====================================================================

def connect(db_file: str = DB_FILE) -> sqlite3.Connection:
    """
    Create and return a connection to the SQLite database.

    Parameters:
        db_file (str): Path to the SQLite database file.

    Returns:
        sqlite3.Connection: Active DB connection with row_factory enabled.

    Raises:
        Error: If the connection to the database fails.
    """
    try:
        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row  # return rows as dictionary-like objects
        conn.execute("PRAGMA foreign_keys = ON")  # sqlite3 does NOT enforce FKs by default!
        return conn
    except Error as exc:
        print(f"Database connection error: {exc}")
        raise


def init_db(sql_path: str = SQL_INIT_FILE, db_file: str = DB_FILE) -> None:
    """
    Initialize the database by executing an SQL creation script.

    The function:
    - Reads a .sql file
    - Executes the SQL commands (CREATE TABLE, INSERT, etc.)
    - Overwrites missing tables

    Parameters:
        sql_path (str): Path to the SQL file.
        db_file (str): Database file to initialize.
    """
    if not Path(sql_path).exists():
        print(f"SQL file not found: {sql_path}. Skip initialization if the DB already exists.")
        return

    conn = connect(db_file)

    with conn, open(sql_path, "r", encoding="utf-8") as sql_file:
        sql_script = sql_file.read()
        conn.executescript(sql_script)

    print("Database initialized from SQL script.")


def print_rows(rows: Iterable[sqlite3.Row]) -> None:
    """
    Pretty-print rows in a table format.

    Parameters:
        rows (iterable): Iterable of sqlite3.Row objects.
    """
    row_list = list(rows)

    if not row_list:
        print("(No results)")
        return

    headers = row_list[0].keys()

    # Determine column widths dynamically
    col_widths = {
        header: max(len(header), *(len(str(row[header])) for row in row_list))
        for header in headers
    }

    # Print header
    header_line = " | ".join(f"{header:<{col_widths[header]}}" for header in headers)
    separator_line = "-+-".join("-" * col_widths[header] for header in headers)

    print(header_line)
    print(separator_line)

    # Print rows
    for row in row_list:
        print(" | ".join(f"{str(row[header]):<{col_widths[header]}}" for header in headers))


# =====================================================================
# ----------------------- Artist table operations ----------------------
# =====================================================================

def list_artists(conn: sqlite3.Connection, order_by: str = "artist_id") -> None:
    """
    List all artists, ordered by a chosen column.

    Parameters:
        conn (Connection): Active DB connection.
        order_by (str): One of {"artist_id", "name", "country"}.
    """
    allowed = {"artist_id", "name", "country"}
    if order_by not in allowed:
        order_by = "artist_id"

    cur = conn.execute(
        f"SELECT artist_id, name, country FROM Artist ORDER BY {order_by} COLLATE NOCASE"
    )
    print_rows(cur.fetchall())


def search_artists(conn: sqlite3.Connection,
                   name_like: Optional[str] = None,
                   country: Optional[str] = None) -> None:
    """
    Search artists by name substring and/or country.

    Parameters:
        conn (Connection): Active DB connection.
        name_like (str|None): Case-insensitive search pattern for name.
        country (str|None): Exact match filter for country.
    """
    query = "SELECT artist_id, name, country FROM Artist WHERE 1=1"
    params: Tuple = tuple()

    # Append filters dynamically
    if name_like:
        query += " AND name LIKE ?"
        params += (f"%{name_like}%",)

    if country:
        query += " AND country = ?"
        params += (country,)

    query += " ORDER BY name COLLATE NOCASE"

    print("QUERY TO BE EXECUTED:")
    print(query, params)
    cur = conn.execute(query, params)
    print_rows(cur.fetchall())


def insert_artist(conn: sqlite3.Connection, name: str, country: Optional[str]) -> int:
    """
    Insert a new artist into the database.

    Parameters:
        conn (Connection): Active DB connection.
        name (str): Artist name (cannot be empty).
        country (str|None): Country code or None.

    Returns:
        int: ID of the inserted artist.
    """
    if not name.strip():
        raise ValueError("Name cannot be empty.")

    with conn:
        cur = conn.execute(
            "INSERT INTO Artist(name, country) VALUES(?, ?)",
            (name.strip(), country)
        )

    print(f"Inserted artist: {name} ({country or '-'}) id={cur.lastrowid}")
    return cur.lastrowid


def update_artist(conn: sqlite3.Connection,
                  artist_id: int,
                  *,
                  name: Optional[str] = None,
                  country: Optional[str] = None) -> None:
    """
    Update an artist's name and/or country.

    Parameters:
        conn (Connection): Active DB connection.
        artist_id (int): ID of the artist to modify.
        name (str|None): New name or None.
        country (str|None): New country or None.
    """
    sets = []
    params = []

    if name is not None:
        if not name.strip():
            raise ValueError("Name cannot be empty.")
        sets.append("name = ?")
        params.append(name.strip())

    if country is not None:
        sets.append("country = ?")
        params.append(country)

    if not sets:
        print("Nothing to update.")
        return

    params.append(artist_id)

    with conn:
        result = conn.execute(
            f"UPDATE Artist SET {', '.join(sets)} WHERE artist_id = ?",
            params
        )

    if result.rowcount == 0:
        print("No artist found with the given ID.")
    else:
        print(f"Updated {result.rowcount} row(s).")


def delete_artist(conn: sqlite3.Connection, artist_id: int) -> None:
    """
    Delete an artist from the database.

    Parameters:
        conn (Connection): Active DB connection.
        artist_id (int): ID of the artist to delete.
    """
    with conn:
        result = conn.execute(
            "DELETE FROM Artist WHERE artist_id = ?",
            (artist_id,)
        )

    if result.rowcount == 0:
        print("No artist found with the given ID.")
    else:
        print(f"Deleted {result.rowcount} row(s).")


# =====================================================================
# -------------------- My Festival M8 additions -----------------------
# =====================================================================

def hae_ohjelma(conn: sqlite3.Connection, haku_syote: str) -> None:
    """Etsii esiintymiset päivämäärän TAI genren perusteella."""
    print(f"\n--- Ohjelmahaku: '{haku_syote}' ---")
    
    sql = """
        SELECT DISTINCT 
            e.start_dt AS aika, 
            s.name AS lava, 
            a.name AS artisti, 
            e.title AS tapahtuma
        FROM Event e
        LEFT JOIN Stage s ON e.stage_id = s.stage_id
        LEFT JOIN Artist a ON e.artist_id = a.artist_id
        LEFT JOIN ArtistGenre ag ON a.artist_id = ag.artist_id
        LEFT JOIN Genre g ON ag.genre_id = g.genre_id
        WHERE e.start_dt LIKE ? OR g.name LIKE ?
        ORDER BY e.start_dt ASC;
    """
    
    syote_muokattu = f"%{haku_syote}%"
    cur = conn.execute(sql, (syote_muokattu, syote_muokattu))
    print_rows(cur.fetchall())


def lisaa_artisti_genreilla(conn: sqlite3.Connection, nimi: str, maa: Optional[str], genret: list[str]) -> None:
    """Lisää artistin ja genret transaktion sisällä."""
    if not nimi.strip():
        print("Virhe: Nimi ei saa olla tyhjä.")
        return

    try:
        with conn: # Transaktio alkaa tästä
            cur = conn.execute(
                "INSERT INTO Artist (name, country) VALUES (?, ?)",
                (nimi.strip(), maa)
            )
            artist_id = cur.lastrowid
            
            for g_nimi in genret:
                g_nimi = g_nimi.strip()
                if not g_nimi:
                    continue
                
                # Etsitään genreä
                g_cur = conn.execute("SELECT genre_id FROM Genre WHERE name = ?", (g_nimi,))
                g_rivi = g_cur.fetchone()
                
                if g_rivi:
                    genre_id = g_rivi['genre_id']
                else:
                    # Luodaan uusi genre
                    g_insert = conn.execute("INSERT INTO Genre (name) VALUES (?)", (g_nimi,))
                    genre_id = g_insert.lastrowid
                
                # Yhdistetään
                conn.execute(
                    "INSERT INTO ArtistGenre (artist_id, genre_id) VALUES (?, ?)",
                    (artist_id, genre_id)
                )
        print(f"Artisti '{nimi}' lisätty onnistuneesti!")
        
    except sqlite3.IntegrityError as e:
        if "UNIQUE constraint failed: Artist.name" in str(e):
            print(f"Virhe: Artisti nimeltä '{nimi}' on jo olemassa tietokannassa.")
        else:
            print(f"Tietokantavirhe: {e}")


def soundcheck_raportti(conn: sqlite3.Connection, pvm: str) -> None:
    """Tulostaa soundcheckit lavoittain ja varoittaa puuttuvista."""
    print(f"\n--- Soundcheck-raportti päivälle {pvm} ---")
    
    # Haetaan soundcheckit (oletetaan että title sisältää sanan 'Soundcheck')
    sql = """
        SELECT s.name AS lava, e.title AS otsikko
        FROM Event e
        JOIN Stage s ON e.stage_id = s.stage_id
        WHERE e.start_dt LIKE ? AND e.title LIKE '%Soundcheck%'
        ORDER BY s.name, e.start_dt;
    """
    
    cur = conn.execute(sql, (f"{pvm}%",))
    rivit = cur.fetchall()
    
    if not rivit:
        print(f"Päivälle {pvm} ei löytynyt soundcheckejä.")
        return

    lavat = {}
    for rivi in rivit:
        lava = rivi['lava']
        if lava not in lavat:
            lavat[lava] = []
        lavat[lava].append(rivi['otsikko'])

    for lava, otsikot in lavat.items():
        print(f"\nLava: {lava}")
        for otsikko in otsikot:
            print(f"  - {otsikko}")
            
    # Tarkistetaan puuttuvat
    kaikki_lavat = conn.execute("SELECT name FROM Stage").fetchall()
    for kl in kaikki_lavat:
        if kl['name'] not in lavat:
            print(f"VAROITUS: Lavalla '{kl['name']}' ei ole soundcheckiä päivänä {pvm}!")

# =====================================================================
# ------------------------- CLI helper tools ---------------------------
# =====================================================================



def ask_int(prompt: str) -> Optional[int]:
    """
    Safely ask the user to input an integer.

    Returns:
        int or None: Parsed number or None if empty/invalid.
    """
    value = input(prompt).strip()
    if value == "":
        return None

    try:
        return int(value)
    except ValueError:
        print("Input must be a number.")
        return None


def menu() -> None:
    """Print the main menu."""
    print("\n=== Festival DB - Artists ===")
    print("1) List artists (ID, name, country)")
    print("2) Search artists (name contains / country)")
    print("3) Insert new artist")
    print("4) Update artist")
    print("5) Delete artist")
    print("6) Initialize database from SQL script")
    print("7) Ohjelmahaku (päivä tai genre)")
    print("8) Lisää artisti genreillä")
    print("9) Soundcheck-raportti")
    print("0) Exit")

# =====================================================================
# ------------------------------ Main ----------------------------------
# =====================================================================

def main() -> None:
    """
    Main CLI loop for interacting with the Artist table.
    """
    conn = connect(DB_FILE)

    while True:
        menu()
        choice = input("Choice: ").strip()

        if choice == "1":
            order = input("Order by (artist_id/name/country) [artist_id]: ").strip() or "artist_id"
            list_artists(conn, order_by=order)

        elif choice == "2":
            name_like = input("Name contains (Enter to skip): ").strip() or None
            country = input("Country (exact, Enter to skip): ").strip() or None
            search_artists(conn, name_like=name_like, country=country)

        elif choice == "3":
            name = input("Name: ").strip()
            country = input("Country (optional): ").strip() or None
            try:
                insert_artist(conn, name, country)
            except Exception as exc:
                print(f"Insertion failed: {exc}")

        elif choice == "4":
            artist_id = ask_int("Artist ID: ")
            if artist_id is None:
                continue
            name = input("New name (Enter = no change): ")
            country = input("New country (Enter = no change): ")
            update_artist(
                conn,
                artist_id,
                name=(name if name != "" else None),
                country=(country if country != "" else None),
            )

        elif choice == "5":
            artist_id = ask_int("Artist ID to delete: ")
            if artist_id is None:
                continue
            delete_artist(conn, artist_id)

        elif choice == "6":
            path = input(f"SQL script path [{SQL_INIT_FILE}]: ").strip() or SQL_INIT_FILE
            try:
                init_db(path, DB_FILE)
            except Exception as exc:
                print(f"Initialization failed: {exc}")

                        # ... (aiemmat vaihtoehdot 1-6 ovat tässä) ...

        elif choice == "7":
            syote = input("Anna päivämäärä (YYYY-MM-DD) tai genre: ").strip()
            hae_ohjelma(conn, syote)

        elif choice == "8":
            nimi = input("Artistin nimi: ").strip()
            maa = input("Maa (valinnainen): ").strip() or None
            
            # Kysytään genret
            g1 = input("Genre 1: ").strip()
            g2 = input("Genre 2 (valinnainen): ").strip()
            
            # Kerätään listaan vain ei-tyhjät
            genret = [g for g in (g1, g2) if g]
            
            lisaa_artisti_genreilla(conn, nimi, maa, genret)

        elif choice == "9":
            pvm = input("Anna päivämäärä (esim. 2025-07-04): ").strip()
            soundcheck_raportti(conn, pvm)

        elif choice == "0":
            break

        elif choice == "0":
            break

        else:
            print("Unknown choice.")

    conn.close()
    print("Goodbye!")


if __name__ == "__main__":
    main()
