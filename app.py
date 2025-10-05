# -----------------------------------------------------------------------------
# Email Contact Database - Final AWS Project
# Author: Andrii Mashtaler
# Description: Flask app for storing & retrieving email contacts.
# Notes:
# - Works locally (SQLite) with ZERO cost.
# - In AWS, prefers direct ENV (DB_* / RDS_*) for MySQL (RDS).
# - Optionally reads creds from AWS Secrets Manager via SECRET_ARN.
# -----------------------------------------------------------------------------

import os
import json
import boto3
from botocore.exceptions import ClientError
from flask import Flask, render_template, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

# ---- Environment -------------------------------------------------------------
AWS_REGION = os.getenv("AWS_REGION", "eu-central-1")

DB_HOST = os.getenv("DB_HOST") or os.getenv("RDS_HOSTNAME") or os.getenv("DB_ENDPOINT")
DB_PORT = int(os.getenv("DB_PORT") or os.getenv("RDS_PORT") or 3306)
DB_NAME = os.getenv("DB_NAME") or os.getenv("RDS_DB_NAME")
DB_USER = os.getenv("DB_USER") or os.getenv("RDS_USERNAME")
DB_PASSWORD = os.getenv("DB_PASSWORD") or os.getenv("RDS_PASSWORD")

SECRET_ARN = os.getenv("SECRET_ARN")

# ---- App init ----------------------------------------------------------------
app = Flask(__name__)


def fetch_rds_credentials(secret_arn: str, region: str):
    """
    Read secret from AWS Secrets Manager.
    Supports:
      - JSON: {"username":"...", "password":"..."}
      - Plain string: just password (then username defaults to 'admin')
    """
    try:
        client = boto3.client("secretsmanager", region_name=region)
        resp = client.get_secret_value(SecretId=secret_arn)
        secret_str = resp.get("SecretString")
        if not secret_str:
            return None, None

        # Try JSON first
        try:
            data = json.loads(secret_str)
            username = data.get("username") or data.get("user") or "admin"
            password = data.get("password") or data.get("pass")
            return username, password
        except json.JSONDecodeError:
            # Plain text secret -> treat as password only
            return "admin", secret_str
    except ClientError as e:
        print(f"[SecretsManager] Error: {e}")
        return None, None


def build_sqlalchemy_uri():
    """
    Пріоритет:
      1) Якщо є прямі env-параметри (DB_HOST/DB_NAME/DB_USER/DB_PASSWORD) -> MySQL (RDS).
      2) Якщо вказано SECRET_ARN + (DB_HOST/DB_NAME) -> витягуємо логін/пароль із Secrets Manager.
      3) Інакше SQLite як безкоштовний локальний fallback.
    """
    if DB_HOST and DB_NAME and DB_USER and DB_PASSWORD:
        return f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

    if SECRET_ARN and DB_HOST and DB_NAME:
        username, password = fetch_rds_credentials(SECRET_ARN, AWS_REGION)
        if username and password:
            return (
                f"mysql+pymysql://{username}:{password}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
            )

    return "sqlite:///./email.db"


# Configure SQLAlchemy
app.config["SQLALCHEMY_DATABASE_URI"] = build_sqlalchemy_uri()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "pool_recycle": 280}

db = SQLAlchemy(app)

# ---- DB bootstrap ------------------------------------------------------------
with app.app_context():
    users_table = text(
        """
        CREATE TABLE IF NOT EXISTS users (
            username VARCHAR(255) NOT NULL PRIMARY KEY,
            email    VARCHAR(255) NOT NULL
        );
        """
    )
    db.session.execute(users_table)

    try:
        cnt = db.session.execute(text("SELECT COUNT(*) FROM users")).scalar()
        if not cnt or int(cnt) == 0:
            seed = text(
                """
                INSERT INTO users (username, email) VALUES
                ('andrii', 'andrii@example.com'),
                ('olena',  'olena@example.com'),
                ('max',    'max@example.com');
                """
            )
            db.session.execute(seed)
            db.session.commit()
    except Exception as e:
        print(f"[Bootstrap] Seed skipped due to: {e}")


# ---- Helpers ----------------------------------------------------------------
def find_emails(keyword: str):
    """Safe, parameterized search (захист від SQL injection)."""
    with app.app_context():
        result = db.session.execute(
            text("SELECT username, email FROM users WHERE username LIKE :kw"),
            {"kw": f"%{keyword}%"},
        )
        rows = [(row[0], row[1]) for row in result]
        return rows if rows else "User not found"


def insert_email(name: str, email: str):
    with app.app_context():
        if not name or not email:
            return "Username or email cannot be empty!"
        if "@" not in email or "." not in email:
            return "Please provide a valid email address."

        existed = db.session.execute(
            text("SELECT 1 FROM users WHERE username = :n"),
            {"n": name},
        ).fetchone()

        if existed:
            return f"User {name} already exists."

        db.session.execute(
            text("INSERT INTO users (username, email) VALUES (:n, :e)"),
            {"n": name, "e": email},
        )
        db.session.commit()
        return f"User {name} with email {email} has been added successfully."


# ---- Routes -----------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health():
    return "OK", 200


@app.route("/health/db", methods=["GET"])
def health_db():
    try:
        db.session.execute(text("SELECT 1"))
        return "ok", 200
    except Exception as e:
        return f"db error: {e}", 500


@app.route("/", methods=["GET", "POST"])
def index():
    feedback = None
    if request.method == "POST":
        if "user_keyword" in request.form:  # Find form
            kw = request.form["user_keyword"].strip()
            user_emails = find_emails(kw) if kw else "User not found"
            return render_template("index.html", name_emails=user_emails, feedback=None)
        elif "username" in request.form and "useremail" in request.form:  # Add form
            feedback = insert_email(
                request.form["username"].strip(), request.form["useremail"].strip()
            )
    return render_template("index.html", feedback=feedback, name_emails=None)


# ---- Entry ------------------------------------------------------------------
if __name__ == "__main__":
    # 0€ local run: python app.py  (http://localhost:8000)
    app.run(host="0.0.0.0", port=8000, debug=True)
