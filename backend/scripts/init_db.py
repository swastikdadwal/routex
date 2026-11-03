"""Creates the RouteX role and databases, and writes their settings to backend/.env.

Safe to run again. Reads the PostgreSQL superuser password from
POSTGRES_SUPERUSER_PASSWORD in backend/.env, or asks for it.
"""
import getpass
import secrets
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from psycopg import sql

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


def main() -> None:
    values = dict(dotenv_values(ENV_PATH)) if ENV_PATH.exists() else {}
    superuser_password = values.get("POSTGRES_SUPERUSER_PASSWORD") or getpass.getpass(
        "PostgreSQL password for the 'postgres' user: "
    )
    existing_url = values.get("DATABASE_URL")
    password = (
        existing_url.split(":", 2)[2].split("@", 1)[0] if existing_url else secrets.token_urlsafe(24)
    )

    with psycopg.connect(
        host="localhost", user="postgres", password=superuser_password, dbname="postgres", autocommit=True
    ) as connection:
        role = sql.Identifier("routex")
        exists = connection.execute("select 1 from pg_roles where rolname = 'routex'").fetchone()
        statement = "alter role {} login password {}" if exists else "create role {} login password {}"
        connection.execute(sql.SQL(statement).format(role, sql.Literal(password)))
        for name in ("routex", "routex_test"):
            found = connection.execute("select 1 from pg_database where datname = %s", (name,)).fetchone()
            if not found:
                connection.execute(sql.SQL("create database {} owner {}").format(sql.Identifier(name), role))

    values["DATABASE_URL"] = f"postgresql+psycopg://routex:{password}@localhost:5432/routex"
    values["TEST_DATABASE_URL"] = f"postgresql+psycopg://routex:{password}@localhost:5432/routex_test"
    ENV_PATH.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="ascii")
    print("Database ready.")


if __name__ == "__main__":
    main()
