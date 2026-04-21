from data_access.sql import DatabaseAccessError, fetch_query_dataframe, get_engine


def fetch_data_from_sql(query, raise_on_error=False):
    """Compatibility wrapper for older call sites."""

    try:
        return fetch_query_dataframe(query)
    except DatabaseAccessError:
        if raise_on_error:
            raise
        return None


__all__ = ["DatabaseAccessError", "fetch_data_from_sql", "get_engine"]
