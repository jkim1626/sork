from data_access.sql import DatabaseAccessError, fetch_query_dataframe, fetch_query_dataframe_public, get_engine


def fetch_data_from_sql(query, raise_on_error=False):
    """Compatibility wrapper for older call sites."""

    try:
        return fetch_query_dataframe(query)
    except DatabaseAccessError:
        if raise_on_error:
            raise
        return None


def fetch_data_from_sql_public(query, raise_on_error=False):
    """Fetch data using qplad_public credentials for unauthenticated users."""

    try:
        return fetch_query_dataframe_public(query)
    except DatabaseAccessError:
        if raise_on_error:
            raise
        return None


__all__ = ["DatabaseAccessError", "fetch_data_from_sql", "fetch_data_from_sql_public", "get_engine"]
