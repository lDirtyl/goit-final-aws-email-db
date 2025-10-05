# -----------------------------------------------------------------------------
# Email Contact Database - Final AWS Project
# Author: Andrii Mashtaler
# Description: Flask app for storing & retrieving email contacts.
# Notes:
# - Works locally (SQLite) with ZERO cost.
# - In AWS, reads DB creds from Secrets Manager (JSON or plain string).
# -----------------------------------------------------------------------------

import os
import json
import boto3
from botocore.exceptions import ClientError
from flask import Flask, render_template, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

# ---- Environment -------------------------------------------------------------
DB_ENDPOINT = os.getenv("DB_ENDPOINT")  # e.g. mydb.xxxxxx.rds.amazonaws.com
DB_NAME = os.getenv("DB_NAME")  # e.g. emaildb
AWS_REGION = os.getenv("AWS_REGION", "eu-central-1")
SECRET_ARN = os.getenv("SECRET_ARN")  # ARN of secret with username/password

# ---- App init ----------------------------------------------------------------
app = Flask(__name__)


def build_sqlalchemy_uri():
    """
    Build SQLAlchemy URI.
    - If AWS env vars present -> use MySQL (RDS) + Secrets Manager.
    - Otherwise fallback to SQLite (free, local).
    """
    if DB_ENDPOINT and DB_NAME and SECRET_ARN:
        username, password = fetch_rds_credentials(SECRET_ARN, AWS_REGION)
        # guard: if secret missing, fallback to SQLite to avoid crashing locally
        if not username or not password:
            return "sqlite:///./email.db"
        return f"mysql+pymysql://{username}:{password}@{DB_ENDPOINT}/{DB_NAME}"
    # Local free fallback
    return "sqlite:///./email.db"


def fetch_rds_credentials(secret_arn: str, region: str):
    """
    Read secret from AWS Secrets Manager.
    Supports both:
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
        # Don't print secret; only error message
        print(f"[SecretsManager] Error: {e}")
        return None, None


# Configure SQLAlchemy
app.config["SQLALCHEMY_DATABASE_URI"] = build_sqlalchemy_uri()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# ---- DB bootstrap ------------------------------------------------------------
with app.app_context():
    # Create users table if it does not exist
    users_table = text(
        """
        CREATE TABLE IF NOT EXISTS users (
            username VARCHAR(255) NOT NULL PRIMARY KEY,
            email    VARCHAR(255) NOT NULL
        );
    """
    )
    db.session.execute(users_table)

    # Seed if empty
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


# ---- Helpers ----------------------------------------------------------------
def find_emails(keyword: str):
    """Safe, parameterized search (prevents SQL injection)."""
    with app.app_context():
        result = db.session.execute(
            text("SELECT username, email FROM users WHERE username LIKE :kw"),
            {"kw": f"%{keyword}%"},
        )
        rows = [(row[0], row[1]) for row in result]
        return rows if rows else "User not found"


def insert_email(name: str, email: str):
    with app.app_context():
        # quick validation
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


@app.route("/", methods=["GET", "POST"])
def index():
    feedback = None
    if request.method == "POST":
        if "user_keyword" in request.form:
            kw = request.form["user_keyword"]
            user_emails = find_emails(kw)
            return render_template("index.html", name_emails=user_emails, feedback=None)
        elif "username" in request.form and "useremail" in request.form:
            feedback = insert_email(request.form["username"], request.form["useremail"])
    return render_template("index.html", feedback=feedback, name_emails=None)


# ---- Entry ------------------------------------------------------------------
if __name__ == "__main__":
    # 0€ local run: python app.py  (http://localhost:8000)
    app.run(host="0.0.0.0", port=8000, debug=True)
