from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash
from functools import wraps
from db import get_connection

app = Flask(__name__)
app.secret_key = "ehotelia_secret_key_demo"  # Required for session and flash messages

def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if "user_role" not in session:
                return redirect(url_for("login"))

            if role and session.get("user_role") != role:
                flash("Accès refusé pour ce rôle.")
                return redirect(url_for("index"))

            return f(*args, **kwargs)
        return wrapped
    return decorator


def manager_only():
    return login_required(role="manager")


def client_only():
    return login_required(role="client")


@app.route("/")
def index():
    if "user_role" not in session:
        return redirect(url_for("login"))
    return render_template("index.html")


@app.route("/clients")
def clients():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT client_id, client_name, client_adress, NAS_client, inscription_date
                FROM client
                ORDER BY client_id
            """)
            clients_list = cur.fetchall()

        return render_template("clients.html", clients=clients_list)
    finally:
        conn.close()


@app.route("/add_client", methods=["POST"])
def add_client():
    client_name = request.form["client_name"].strip()
    client_adress = request.form["client_adress"].strip()
    nas_client = request.form["nas_client"].strip()

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO client (client_name, client_adress, NAS_client)
                VALUES (%s, %s, %s)
            """, (client_name, client_adress, nas_client))
        conn.commit()
    finally:
        conn.close()

    return redirect(url_for("clients"))


@app.route("/update_client", methods=["POST"])
def update_client():
    client_id = request.form["client_id"].strip()
    client_name = request.form["client_name"].strip()
    client_adress = request.form["client_adress"].strip()
    nas_client = request.form["nas_client"].strip()

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE client
                SET client_name = %s,
                    client_adress = %s,
                    NAS_client = %s
                WHERE client_id = %s
            """, (client_name, client_adress, nas_client, client_id))
        conn.commit()
    finally:
        conn.close()

    return redirect(url_for("clients"))


@app.route("/delete_client", methods=["POST"])
def delete_client():
    client_id = request.form["client_id"].strip()

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM client
                WHERE client_id = %s
            """, (client_id,))
        conn.commit()
    finally:
        conn.close()

    return redirect(url_for("clients"))


def build_search_query(form_data):
    query = """
        SELECT
            c.chambre_id,
            c.capacity,
            c.superficie,
            c.chambre_prix,
            h.hotel_name,
            h.zone,
            h.categorie,
            h.chambre_nb,
            ch.chaine_name
        FROM chambre c
        JOIN hotel h ON c.hotel_id = h.hotel_id
        JOIN chaine_hoteliere ch ON h.chaine_id = ch.chaine_id
        WHERE 1=1
    """
    params = []

    start_date = form_data.get("start_date", "").strip()
    end_date = form_data.get("end_date", "").strip()
    capacity = form_data.get("capacity", "").strip()
    min_superficie = form_data.get("min_superficie", "").strip()
    chaine_name = form_data.get("chaine_name", "").strip()
    categorie = form_data.get("categorie", "").strip()
    min_chambre_nb = form_data.get("min_chambre_nb", "").strip()
    prix_max = form_data.get("prix_max", "").strip()

    if capacity:
        query += " AND c.capacity = %s"
        params.append(capacity)

    if min_superficie:
        query += " AND c.superficie >= %s"
        params.append(min_superficie)

    if chaine_name:
        query += " AND ch.chaine_name ILIKE %s"
        params.append(f"%{chaine_name}%")

    if categorie:
        query += " AND h.categorie = %s"
        params.append(categorie)

    if min_chambre_nb:
        query += " AND h.chambre_nb >= %s"
        params.append(min_chambre_nb)

    if prix_max:
        query += " AND c.chambre_prix <= %s"
        params.append(prix_max)

    if start_date and end_date:
        query += """
            AND c.chambre_id NOT IN (
                SELECT chambre_id
                FROM reservation_chambre
                WHERE %s < end_date
                  AND %s > start_date
            )
            AND c.chambre_id NOT IN (
                SELECT chambre_id
                FROM location_chambre
                WHERE %s < end_date
                  AND %s > start_date
            )
        """
        params.extend([start_date, end_date, start_date, end_date])

    query += " ORDER BY c.chambre_id"
    return query, params


@app.route("/search", methods=["GET"])
@login_required()
def search():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            query, params = build_search_query({})
            cur.execute(query, params)
            chambres = cur.fetchall()

        return render_template("search.html", chambres=chambres)
    finally:
        conn.close()


@app.route("/search_results", methods=["POST"])
@login_required()
def search_results():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            query, params = build_search_query(request.form)
            cur.execute(query, params)
            rows = cur.fetchall()

        chambres = []
        for row in rows:
            chambres.append({
                "chambre_id": row[0],
                "capacity": row[1],
                "superficie": row[2],
                "chambre_prix": float(row[3]),
                "hotel_name": row[4],
                "zone": row[5],
                "categorie": row[6],
                "chambre_nb": row[7],
                "chaine_name": row[8],
            })

        return jsonify(chambres)
    finally:
        conn.close()
@app.route("/reservation", methods=["GET", "POST"])
@login_required()
def reservation():
    conn = get_connection()
    try:
        user_role = session.get("user_role")
        user_id = session.get("user_id")

        if request.method == "POST":
            chambre_id = request.form["chambre_id"].strip()
            start_date = request.form["start_date"].strip()
            end_date = request.form["end_date"].strip()

            # Si c'est un client connecté, il réserve uniquement pour lui-même
            if user_role == "client":
                client_id = user_id
            else:
                client_id = request.form["client_id"].strip()

            if not start_date or not end_date:
                flash("Veuillez remplir toutes les dates.")
                return redirect(url_for("reservation"))

            if end_date <= start_date:
                flash("La date de fin doit être après la date de début.")
                return redirect(url_for("reservation"))

            with conn.cursor() as cur:
                # Vérifier que le client existe
                cur.execute("""
                    SELECT client_name, NAS_client
                    FROM client
                    WHERE client_id = %s
                """, (client_id,))
                client_row = cur.fetchone()

                if not client_row:
                    flash("Client introuvable.")
                    return redirect(url_for("reservation"))

                client_name, nas_client = client_row

                # Vérifier que la chambre existe
                cur.execute("""
                    SELECT ch.chambre_prix, h.hotel_name
                    FROM chambre ch
                    JOIN hotel h ON h.hotel_id = ch.hotel_id
                    WHERE ch.chambre_id = %s
                """, (chambre_id,))
                chambre_row = cur.fetchone()

                if not chambre_row:
                    flash("Chambre introuvable.")
                    return redirect(url_for("reservation"))

                chambre_prix, hotel_name = chambre_row

                # Vérifier si la chambre est déjà réservée sur ces dates
                cur.execute("""
                    SELECT 1
                    FROM reservation_chambre
                    WHERE chambre_id = %s
                      AND %s < end_date
                      AND %s > start_date
                    LIMIT 1
                """, (chambre_id, start_date, end_date))
                reservation_existante = cur.fetchone()

                # Vérifier si la chambre est déjà louée sur ces dates
                cur.execute("""
                    SELECT 1
                    FROM location_chambre
                    WHERE chambre_id = %s
                      AND %s < end_date
                      AND %s > start_date
                    LIMIT 1
                """, (chambre_id, start_date, end_date))
                location_existante = cur.fetchone()

                if reservation_existante or location_existante:
                    flash("Cette chambre est déjà réservée ou louée pour cette période.")
                    return redirect(url_for("reservation"))

                # Insertion de la réservation
                cur.execute("""
                    INSERT INTO reservation_chambre (
                        start_date,
                        end_date,
                        client_id,
                        reservation_date,
                        chambre_id,
                        client_name,
                        NAS_client,
                        chambre_prix,
                        hotel_name
                    )
                    VALUES (%s, %s, %s, CURRENT_DATE, %s, %s, %s, %s, %s)
                    RETURNING reservation_id
                """, (
                    start_date,
                    end_date,
                    client_id,
                    chambre_id,
                    client_name,
                    nas_client,
                    chambre_prix,
                    hotel_name
                ))

                inserted_row = cur.fetchone()
                conn.commit()

                if inserted_row:
                    flash(f"Réservation ajoutée avec succès. ID = {inserted_row[0]}")
                else:
                    flash("La réservation n'a pas pu être ajoutée.")

                return redirect(url_for("reservation"))

        with conn.cursor() as cur:
            # Si client connecté → seulement lui
            if user_role == "client":
                cur.execute("""
                    SELECT client_id, client_name
                    FROM client
                    WHERE client_id = %s
                """, (user_id,))
                clients = cur.fetchall()
            else:
                cur.execute("""
                    SELECT client_id, client_name
                    FROM client
                    ORDER BY client_id
                """)
                clients = cur.fetchall()

            cur.execute("""
                SELECT chambre_id, capacity, chambre_prix
                FROM chambre
                ORDER BY chambre_id
            """)
            chambres = cur.fetchall()

            # Si client connecté → seulement ses réservations
            if user_role == "client":
                cur.execute("""
                    SELECT reservation_id, client_name, chambre_id, start_date, end_date
                    FROM reservation_chambre
                    WHERE client_id = %s
                    ORDER BY reservation_id
                """, (user_id,))
            else:
                cur.execute("""
                    SELECT reservation_id, client_name, chambre_id, start_date, end_date
                    FROM reservation_chambre
                    ORDER BY reservation_id
                """)
            reservations = cur.fetchall()

            cur.execute("""
                SELECT id_employee, employee_name
                FROM employee
                ORDER BY id_employee
            """)
            employees = cur.fetchall()

        return render_template(
            "reservation.html",
            clients=clients,
            chambres=chambres,
            reservations=reservations,
            employees=employees,
            user_role=user_role,
            user_id=user_id
        )

    finally:
        conn.close()
@app.route("/location", methods=["GET", "POST"])
@login_required()
def location():
    conn = get_connection()
    try:
        user_role = session.get("user_role")
        user_id = session.get("user_id")

        if request.method == "POST":
            chambre_id = request.form["chambre_id"].strip()
            start_date = request.form["start_date"].strip()
            end_date = request.form["end_date"].strip()

            # Client connecté = location seulement pour lui-même
            if user_role == "client":
                client_id = user_id
                id_employee = None
            else:
                client_id = request.form["client_id"].strip()
                id_employee = request.form.get("id_employee", "").strip() or None

            if not start_date or not end_date:
                flash("Veuillez remplir toutes les dates.")
                return redirect(url_for("location"))

            if end_date <= start_date:
                flash("La date de fin doit être après la date de début.")
                return redirect(url_for("location"))

            with conn.cursor() as cur:
                # Vérifier le client
                cur.execute("""
                    SELECT client_name, NAS_client
                    FROM client
                    WHERE client_id = %s
                """, (client_id,))
                client_row = cur.fetchone()

                if not client_row:
                    flash("Client introuvable.")
                    return redirect(url_for("location"))

                client_name, nas_client = client_row

                # Vérifier la chambre
                cur.execute("""
                    SELECT ch.chambre_prix, h.hotel_name
                    FROM chambre ch
                    JOIN hotel h ON h.hotel_id = ch.hotel_id
                    WHERE ch.chambre_id = %s
                """, (chambre_id,))
                chambre_row = cur.fetchone()

                if not chambre_row:
                    flash("Chambre introuvable.")
                    return redirect(url_for("location"))

                chambre_prix, hotel_name = chambre_row

                # Vérifier si la chambre est déjà réservée
                cur.execute("""
                    SELECT 1
                    FROM reservation_chambre
                    WHERE chambre_id = %s
                      AND %s < end_date
                      AND %s > start_date
                    LIMIT 1
                """, (chambre_id, start_date, end_date))
                reservation_existante = cur.fetchone()

                # Vérifier si la chambre est déjà louée
                cur.execute("""
                    SELECT 1
                    FROM location_chambre
                    WHERE chambre_id = %s
                      AND %s < end_date
                      AND %s > start_date
                    LIMIT 1
                """, (chambre_id, start_date, end_date))
                location_existante = cur.fetchone()

                if reservation_existante or location_existante:
                    flash("Cette chambre est déjà réservée ou louée pour cette période.")
                    return redirect(url_for("location"))

                # Insertion location directe
                cur.execute("""
                    INSERT INTO location_chambre (
                        start_date,
                        end_date,
                        chambre_id,
                        id_employee,
                        client_id,
                        client_name,
                        NAS_client,
                        chambre_prix,
                        hotel_name
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING location_id
                """, (
                    start_date,
                    end_date,
                    chambre_id,
                    id_employee,
                    client_id,
                    client_name,
                    nas_client,
                    chambre_prix,
                    hotel_name
                ))

                inserted_row = cur.fetchone()
                conn.commit()

                if inserted_row:
                    flash(f"Location ajoutée avec succès. ID = {inserted_row[0]}")
                else:
                    flash("La location n'a pas pu être ajoutée.")

                return redirect(url_for("location"))

        with conn.cursor() as cur:
            # Si client connecté → seulement lui
            if user_role == "client":
                cur.execute("""
                    SELECT client_id, client_name
                    FROM client
                    WHERE client_id = %s
                """, (user_id,))
                clients = cur.fetchall()
            else:
                cur.execute("""
                    SELECT client_id, client_name
                    FROM client
                    ORDER BY client_id
                """)
                clients = cur.fetchall()

            cur.execute("""
                SELECT chambre_id, capacity, chambre_prix
                FROM chambre
                ORDER BY chambre_id
            """)
            chambres = cur.fetchall()

            if user_role == "manager":
                cur.execute("""
                    SELECT id_employee, employee_name
                    FROM employee
                    ORDER BY id_employee
                """)
                employees = cur.fetchall()
            else:
                employees = []

            # Si client connecté → seulement ses locations
            if user_role == "client":
                cur.execute("""
                    SELECT location_id, client_name, chambre_id, start_date, end_date
                    FROM location_chambre
                    WHERE client_id = %s
                    ORDER BY location_id
                """, (user_id,))
            else:
                cur.execute("""
                    SELECT location_id, client_name, chambre_id, start_date, end_date
                    FROM location_chambre
                    ORDER BY location_id
                """)
            locations = cur.fetchall()

        return render_template(
            "location.html",
            clients=clients,
            chambres=chambres,
            employees=employees,
            locations=locations,
            user_role=user_role,
            user_id=user_id
        )
    finally:
        conn.close()


@app.route("/convert_reservation", methods=["POST"])
@manager_only()
def convert_reservation():
    reservation_id = request.form["reservation_id"].strip()
    id_employee = request.form["id_employee"].strip()

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT start_date, end_date, chambre_id, client_id,
                       client_name, NAS_client, chambre_prix, hotel_name
                FROM reservation_chambre
                WHERE reservation_id = %s
            """, (reservation_id,))
            reservation = cur.fetchone()

            if reservation:
                start_date, end_date, chambre_id, client_id, client_name, nas_client, chambre_prix, hotel_name = reservation

                cur.execute("""
                    INSERT INTO location_chambre (
                        start_date, end_date, chambre_id, id_employee, client_id,
                        client_name, NAS_client, chambre_prix, hotel_name
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    start_date, end_date, chambre_id, id_employee, client_id,
                    client_name, nas_client, chambre_prix, hotel_name
                ))

                cur.execute("""
                    DELETE FROM reservation_chambre
                    WHERE reservation_id = %s
                """, (reservation_id,))

                conn.commit()

    finally:
        conn.close()

    return redirect(url_for("reservation"))
@app.route("/chambres", methods=["GET"])
@manager_only()
def chambres():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT c.chambre_id, c.capacity, c.superficie, c.chambre_prix,
                       c.add_bed_option, c.vue, c.etat, c.hotel_id, h.hotel_name
                FROM chambre c
                JOIN hotel h ON c.hotel_id = h.hotel_id
                ORDER BY c.chambre_id
            """)
            chambres_list = cur.fetchall()

            cur.execute("""
                SELECT hotel_id, hotel_name
                FROM hotel
                ORDER BY hotel_id
            """)
            hotels = cur.fetchall()

        return render_template("chambres.html", chambres=chambres_list, hotels=hotels)
    finally:
        conn.close()


@app.route("/add_chambre", methods=["POST"])
@manager_only()
def add_chambre():
    capacity = request.form["capacity"].strip()
    superficie = request.form["superficie"].strip()
    chambre_prix = request.form["chambre_prix"].strip()
    add_bed_option = request.form["add_bed_option"].strip()
    vue = request.form["vue"].strip()
    etat = request.form["etat"].strip()
    hotel_id = request.form["hotel_id"].strip()

    add_bed_bool = add_bed_option == "true"

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO chambre (
                    capacity, hotel_id, add_bed_option, chambre_prix, vue, etat, superficie
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (capacity, hotel_id, add_bed_bool, chambre_prix, vue, etat, superficie))
        conn.commit()
    finally:
        conn.close()

    return redirect(url_for("chambres"))


@app.route("/update_chambre", methods=["POST"])
@manager_only()
def update_chambre():
    chambre_id = request.form["chambre_id"].strip()
    capacity = request.form["capacity"].strip()
    superficie = request.form["superficie"].strip()
    chambre_prix = request.form["chambre_prix"].strip()
    add_bed_option = request.form["add_bed_option"].strip()
    vue = request.form["vue"].strip()
    etat = request.form["etat"].strip()
    hotel_id = request.form["hotel_id"].strip()

    add_bed_bool = add_bed_option == "true"

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE chambre
                SET capacity = %s,
                    superficie = %s,
                    chambre_prix = %s,
                    add_bed_option = %s,
                    vue = %s,
                    etat = %s,
                    hotel_id = %s
                WHERE chambre_id = %s
            """, (capacity, superficie, chambre_prix, add_bed_bool, vue, etat, hotel_id, chambre_id))
        conn.commit()
    finally:
        conn.close()

    return redirect(url_for("chambres"))


@app.route("/delete_chambre", methods=["POST"])
@manager_only()
def delete_chambre():
    chambre_id = request.form["chambre_id"].strip()

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM chambre WHERE chambre_id = %s", (chambre_id,))
        conn.commit()
    finally:
        conn.close()

    return redirect(url_for("chambres"))
@app.route("/hotels", methods=["GET"])
@manager_only()
def hotels():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT h.hotel_id, h.hotel_name, h.hotel_adress, h.hotel_telephone,
                       h.hotel_email, h.chambre_nb, h.categorie, h.chaine_id,
                       h.id_manager, h.zone, c.chaine_name
                FROM hotel h
                JOIN chaine_hoteliere c ON h.chaine_id = c.chaine_id
                ORDER BY h.hotel_id
            """)
            hotels_list = cur.fetchall()

            cur.execute("""
                SELECT chaine_id, chaine_name
                FROM chaine_hoteliere
                ORDER BY chaine_id
            """)
            chaines = cur.fetchall()

            cur.execute("""
                SELECT id_employee, employee_name
                FROM employee
                ORDER BY id_employee
            """)
            employees = cur.fetchall()

        return render_template(
            "hotels.html",
            hotels=hotels_list,
            chaines=chaines,
            employees=employees
        )
    finally:
        conn.close()


@app.route("/add_hotel", methods=["POST"])
@manager_only()
def add_hotel():
    hotel_name = request.form["hotel_name"].strip()
    hotel_adress = request.form["hotel_adress"].strip()
    hotel_telephone = request.form["hotel_telephone"].strip()
    hotel_email = request.form["hotel_email"].strip()
    chambre_nb = request.form["chambre_nb"].strip()
    categorie = request.form["categorie"].strip()
    chaine_id = request.form["chaine_id"].strip()
    id_manager = request.form["id_manager"].strip()
    zone = request.form["zone"].strip()

    if id_manager == "":
        id_manager = None

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO hotel (
                    hotel_name, hotel_adress, hotel_telephone, hotel_email,
                    chambre_nb, categorie, chaine_id, id_manager, zone
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                hotel_name, hotel_adress, hotel_telephone, hotel_email,
                chambre_nb, categorie, chaine_id, id_manager, zone
            ))
        conn.commit()
    finally:
        conn.close()

    return redirect(url_for("hotels"))


@app.route("/update_hotel", methods=["POST"])
@manager_only()
def update_hotel():
    hotel_id = request.form["hotel_id"].strip()
    hotel_name = request.form["hotel_name"].strip()
    hotel_adress = request.form["hotel_adress"].strip()
    hotel_telephone = request.form["hotel_telephone"].strip()
    hotel_email = request.form["hotel_email"].strip()
    chambre_nb = request.form["chambre_nb"].strip()
    categorie = request.form["categorie"].strip()
    chaine_id = request.form["chaine_id"].strip()
    id_manager = request.form["id_manager"].strip()
    zone = request.form["zone"].strip()

    if id_manager == "":
        id_manager = None

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE hotel
                SET hotel_name = %s,
                    hotel_adress = %s,
                    hotel_telephone = %s,
                    hotel_email = %s,
                    chambre_nb = %s,
                    categorie = %s,
                    chaine_id = %s,
                    id_manager = %s,
                    zone = %s
                WHERE hotel_id = %s
            """, (
                hotel_name, hotel_adress, hotel_telephone, hotel_email,
                chambre_nb, categorie, chaine_id, id_manager, zone, hotel_id
            ))
        conn.commit()
    finally:
        conn.close()

    return redirect(url_for("hotels"))


@app.route("/delete_hotel", methods=["POST"])
@manager_only()
def delete_hotel():
    hotel_id = request.form["hotel_id"].strip()

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM hotel
                WHERE hotel_id = %s
            """, (hotel_id,))
        conn.commit()
    finally:
        conn.close()

    return redirect(url_for("hotels"))


@app.route("/employees", methods=["GET"])
@manager_only()
def employees():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT e.id_employee, e.employee_name, e.employee_adress,
                       e.role, e.NAS_employee, e.hotel_id, h.hotel_name
                FROM employee e
                JOIN hotel h ON e.hotel_id = h.hotel_id
                ORDER BY e.id_employee
            """)
            employees_list = cur.fetchall()

            cur.execute("""
                SELECT hotel_id, hotel_name
                FROM hotel
                ORDER BY hotel_id
            """)
            hotels = cur.fetchall()

        return render_template("employees.html", employees=employees_list, hotels=hotels)
    finally:
        conn.close()


@app.route("/add_employee", methods=["POST"])
@manager_only()
def add_employee():
    employee_name = request.form["employee_name"].strip()
    employee_adress = request.form["employee_adress"].strip()
    role = request.form["role"].strip()
    nas_employee = request.form["nas_employee"].strip()
    hotel_id = request.form["hotel_id"].strip()

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO employee (
                    employee_name, employee_adress, role, NAS_employee, hotel_id
                )
                VALUES (%s, %s, %s, %s, %s)
            """, (
                employee_name, employee_adress, role, nas_employee, hotel_id
            ))
        conn.commit()
    finally:
        conn.close()

    return redirect(url_for("employees"))


@app.route("/update_employee", methods=["POST"])
@manager_only()
def update_employee():
    id_employee = request.form["id_employee"].strip()
    employee_name = request.form["employee_name"].strip()
    employee_adress = request.form["employee_adress"].strip()
    role = request.form["role"].strip()
    nas_employee = request.form["nas_employee"].strip()
    hotel_id = request.form["hotel_id"].strip()

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE employee
                SET employee_name = %s,
                    employee_adress = %s,
                    role = %s,
                    NAS_employee = %s,
                    hotel_id = %s
                WHERE id_employee = %s
            """, (
                employee_name, employee_adress, role, nas_employee, hotel_id, id_employee
            ))
        conn.commit()
    finally:
        conn.close()

    return redirect(url_for("employees"))


@app.route("/delete_employee", methods=["POST"])
@manager_only()
def delete_employee():
    id_employee = request.form["id_employee"].strip()

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM employee
                WHERE id_employee = %s
            """, (id_employee,))
        conn.commit()
    finally:
        conn.close()

    return redirect(url_for("employees"))
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user_type = request.form["user_type"].strip()
        user_id = request.form["user_id"].strip()

        conn = get_connection()
        try:
            with conn.cursor() as cur:
                if user_type == "manager":
                    cur.execute("""
                        SELECT id_employee, employee_name
                        FROM employee
                        WHERE id_employee = %s AND role = 'manager'
                    """, (user_id,))
                    user = cur.fetchone()

                    if user:
                        session["user_id"] = user[0]
                        session["user_name"] = user[1]
                        session["user_role"] = "manager"
                        return redirect(url_for("index"))

                elif user_type == "client":
                    cur.execute("""
                        SELECT client_id, client_name
                        FROM client
                        WHERE client_id = %s
                    """, (user_id,))
                    user = cur.fetchone()

                    if user:
                        session["user_id"] = user[0]
                        session["user_name"] = user[1]
                        session["user_role"] = "client"
                        return redirect(url_for("index"))

            flash("Identifiant invalide.")
            return redirect(url_for("login"))
        finally:
            conn.close()

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))
if __name__ == "__main__":
    app.run(debug=True)