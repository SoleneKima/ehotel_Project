import psycopg2
from psycopg2.extensions import connection as PGConnection


def get_connection() -> PGConnection:
    """
    Ouvre une connexion PostgreSQL et force le schéma ehotel
    comme schéma par défaut pour cette session.
    """
    conn = psycopg2.connect(
        dbname="ehotel",
        user="solene",
        password="011716",
        host="localhost",
        port="5432",
    )

    with conn.cursor() as cur:
        cur.execute("SET search_path TO ehotel;")

    return conn