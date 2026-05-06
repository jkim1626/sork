import logging
import os
import re

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(override=True)

logger = logging.getLogger(__name__)


# Mapping of table names to descriptive labels
TABLE_DESCRIPTIONS = {
    "db_main": "Growth/Survival Data",
    "budburst_date1": "Budburst Dates",
    "budburst_detailed_all": "All Budburst Stages",
    "biomass_2021_combined_fordb_052224": "Biomass 2021",
    "leaf_traits_2016": "Leaf Traits 2016",
    "dat_climdb": "Climate Database",
    "dat_cgp_db": "Common Garden Phenotypes",
    "dat_avail_db": "Data Availability Metadata",
}


class DatabaseAccessError(Exception):
    """Raised when a database operation cannot be completed safely."""


def get_table_display_name(table_name):
    """Get the descriptive display name for a table."""
    return TABLE_DESCRIPTIONS.get(table_name, table_name)


_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_ ]*$")


def _build_connection_string(server_var="DB_SERVER", db_var="DB_DATABASE", user_var="DB_USERNAME", pass_var="DB_PASSWORD"):
    driver = "ODBC Driver 17 for SQL Server"
    server = os.getenv(server_var)
    database = os.getenv(db_var)
    username = os.getenv(user_var)
    password = os.getenv(pass_var)

    if not all([server, database, username, password]):
        raise DatabaseAccessError(f"Missing one or more database environment variables for {server_var}.")

    return (
        f"mssql+pyodbc://{username}:{password}@{server}/{database}"
        f"?driver={driver}&Encrypt=yes&TrustServerCertificate=yes"
    )


def _public_creds_configured():
    """Return True only if all four DB_PUBLIC_* env vars are set and non-placeholder."""
    for var in ("DB_PUBLIC_SERVER", "DB_PUBLIC_DATABASE", "DB_PUBLIC_USERNAME", "DB_PUBLIC_PASSWORD"):
        val = os.getenv(var, "")
        if not val or "_here" in val or val.lower() in ("none", ""):
            return False
    return True


def get_engine(connection_type="read"):
    """Get SQLAlchemy engine for specified connection type.

    connection_type: 'read', 'upload', or 'public'.

    If connection_type is 'public' but the DB_PUBLIC_* env vars are not
    configured yet, the function falls back to the standard read engine and
    logs a warning rather than crashing.
    """
    if connection_type == "upload":
        connection_string = _build_connection_string(
            server_var="DB_UPLOAD_SERVER",
            db_var="DB_UPLOAD_DATABASE",
            user_var="DB_UPLOAD_USERNAME",
            pass_var="DB_UPLOAD_PASSWORD"
        )
    elif connection_type == "public":
        if _public_creds_configured():
            connection_string = _build_connection_string(
                server_var="DB_PUBLIC_SERVER",
                db_var="DB_PUBLIC_DATABASE",
                user_var="DB_PUBLIC_USERNAME",
                pass_var="DB_PUBLIC_PASSWORD"
            )
        else:
            logger.warning(
                "DB_PUBLIC_* credentials are not configured. "
                "Falling back to the read engine for public queries. "
                "Set DB_PUBLIC_SERVER / DB_PUBLIC_DATABASE / DB_PUBLIC_USERNAME / "
                "DB_PUBLIC_PASSWORD in .env to use the dedicated qplad_public role."
            )
            connection_string = _build_connection_string()
    else:  # read (default)
        connection_string = _build_connection_string()

    return create_engine(
        connection_string,
        fast_executemany=True,
        pool_pre_ping=True,
    )


def get_allowed_tables():
    table_options = os.getenv("TABLE_OPTIONS", "")
    return [table.strip() for table in table_options.split(",") if table.strip()]


def _quote_identifier(identifier):
    if not identifier or not _IDENTIFIER_PATTERN.fullmatch(identifier):
        raise DatabaseAccessError(f"Unsafe SQL identifier: {identifier!r}")
    return f"[{identifier}]"


def _validate_table_name(table_name):
    if table_name not in get_allowed_tables():
        raise DatabaseAccessError(f"Table '{table_name}' is not available in this app.")
    return table_name


def fetch_query_dataframe(query, connection_type="read"):
    """Execute a query and return a DataFrame.

    connection_type: 'read' (default authenticated), 'upload', or 'public'.
    """
    engine = None
    try:
        engine = get_engine(connection_type)
        with engine.connect() as connection:
            return pd.read_sql_query(query, connection)
    except DatabaseAccessError:
        raise
    except Exception as exc:
        raise DatabaseAccessError(f"Database query failed: {exc}") from exc
    finally:
        if engine is not None:
            engine.dispose()


def fetch_query_dataframe_public(query):
    """Execute a query using the qplad_public role (unauthenticated users)."""
    return fetch_query_dataframe(query, connection_type="public")


def get_table_columns(table_name):
    validated_table = _validate_table_name(table_name)
    query = text("""
    SELECT COLUMN_NAME
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = :table_name
    ORDER BY ORDINAL_POSITION
    """)
    engine = None
    try:
        engine = get_engine()
        with engine.connect() as connection:
            df = pd.read_sql_query(query, connection, params={"table_name": validated_table})
    except Exception as exc:
        raise DatabaseAccessError(f"Unable to load columns for '{validated_table}': {exc}") from exc
    finally:
        if engine is not None:
            engine.dispose()

    if df.empty:
        raise DatabaseAccessError(f"Table '{validated_table}' does not expose any columns.")

    return df["COLUMN_NAME"].tolist()


def get_table_schema_preview(table_name):
    validated_table = _validate_table_name(table_name)
    query = """
    SELECT COLUMN_NAME, DATA_TYPE
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = :table_name
    ORDER BY ORDINAL_POSITION
    """
    engine = None
    try:
        engine = get_engine()
        with engine.connect() as connection:
            return pd.read_sql_query(query, connection, params={"table_name": validated_table})
    except Exception as exc:
        raise DatabaseAccessError(f"Unable to load schema for '{validated_table}': {exc}") from exc
    finally:
        if engine is not None:
            engine.dispose()


def get_table_preview(table_name, limit=1):
    validated_table = _validate_table_name(table_name)
    safe_limit = max(1, int(limit))
    query = f"SELECT TOP {safe_limit} * FROM [dbo].{_quote_identifier(validated_table)}"
    return fetch_query_dataframe(query)


def get_table_row_count(table_name):
    validated_table = _validate_table_name(table_name)
    query = f"SELECT COUNT(*) AS row_count FROM [dbo].{_quote_identifier(validated_table)}"
    df = fetch_query_dataframe(query)
    return int(df.iloc[0]["row_count"])


def get_column_distinct_values(table_name, column, limit=200):
    validated_table = _validate_table_name(table_name)
    available_columns = get_table_columns(validated_table)
    if column not in available_columns:
        raise DatabaseAccessError(f"Unknown column '{column}' for '{validated_table}'.")

    safe_limit = max(1, int(limit or 200))
    query = f"""
    SELECT TOP {safe_limit} {_quote_identifier(column)} AS value
    FROM [dbo].{_quote_identifier(validated_table)}
    WHERE {_quote_identifier(column)} IS NOT NULL
    GROUP BY {_quote_identifier(column)}
    ORDER BY {_quote_identifier(column)}
    """
    df = fetch_query_dataframe(query)
    return df["value"].tolist() if not df.empty else []


def fetch_table_rows(table_name, columns, start_row=1, row_count=100, max_rows=None, filters=None):
    validated_table = _validate_table_name(table_name)
    available_columns = get_table_columns(validated_table)

    if not columns:
        raise DatabaseAccessError("Select at least one column.")

    invalid_columns = [column for column in columns if column not in available_columns]
    if invalid_columns:
        raise DatabaseAccessError(
            f"Unknown column selection for '{validated_table}': {', '.join(invalid_columns)}"
        )

    safe_start = max(int(start_row or 1), 1)
    safe_count = max(int(row_count or 1), 1)
    if max_rows is not None:
        safe_count = min(safe_count, int(max_rows))

    where_clauses = []
    for column, values in (filters or {}).items():
        if column not in available_columns:
            raise DatabaseAccessError(f"Unknown filter column '{column}' for '{validated_table}'.")
        clean_values = [value for value in (values or []) if value not in (None, "")]
        if clean_values:
            literals = ", ".join("'" + str(value).replace("'", "''") + "'" for value in clean_values)
            where_clauses.append(f"{_quote_identifier(column)} IN ({literals})")

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    quoted_columns = ", ".join(_quote_identifier(column) for column in columns)
    query = f"""
    SELECT {quoted_columns}
    FROM [dbo].{_quote_identifier(validated_table)}
    {where_sql}
    ORDER BY (SELECT NULL)
    OFFSET {safe_start - 1} ROWS
    FETCH NEXT {safe_count} ROWS ONLY
    """
    return fetch_query_dataframe(query)


def append_dataframe_to_table(table_name, df):
    validated_table = _validate_table_name(table_name)
    expected_columns = get_table_columns(validated_table)

    if df.empty:
        raise DatabaseAccessError("The uploaded CSV contains no data rows.")

    if len(df.columns) != len(expected_columns):
        raise DatabaseAccessError(
            f"Expected {len(expected_columns)} columns for '{validated_table}', got {len(df.columns)}."
        )
    if list(df.columns) != expected_columns:
        raise DatabaseAccessError(
            "CSV columns must match the destination table exactly and in order. "
            f"Expected: {', '.join(expected_columns)}."
        )

    upload_df = df.copy()
    upload_df = upload_df.where(pd.notnull(upload_df), None)

    engine = None
    try:
        engine = get_engine("upload")  # Use upload credentials for INSERT operations
        with engine.begin() as connection:
            upload_df.to_sql(validated_table, connection, if_exists="append", index=False, schema="dbo")
    except Exception as exc:
        raise DatabaseAccessError(f"Database upload failed: {exc}") from exc
    finally:
        if engine is not None:
            engine.dispose()

    return len(upload_df)
