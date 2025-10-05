import os
import pymysql


def get_conn():
    return pymysql.connect(
        host=os.getenv("DB_HOST", os.getenv("RDS_HOSTNAME")),
        user=os.getenv("DB_USER", os.getenv("RDS_USERNAME")),
        password=os.getenv("DB_PASSWORD", os.getenv("RDS_PASSWORD")),
        database=os.getenv("DB_NAME", os.getenv("RDS_DB_NAME")),
        port=int(os.getenv("DB_PORT", os.getenv("RDS_PORT", "3306"))),
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=5,
    )


def create_table_if_needed():
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS emails (
                username VARCHAR(255) PRIMARY KEY,
                email    VARCHAR(255) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        )
        conn.commit()


def add_email(username, email):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "REPLACE INTO emails (username, email) VALUES (%s, %s)", (username, email)
        )
        conn.commit()


def find_email(username):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT email FROM emails WHERE username=%s", (username,))
        row = cur.fetchone()
        return row["email"] if row else None
