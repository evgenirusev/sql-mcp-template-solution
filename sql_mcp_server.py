"""SQL MCP Server - Database operations via Model Context Protocol."""

from typing import List, Dict, Any
import os
import contextlib
import logging

import pyodbc  # type: ignore
from mcp.server.fastmcp import FastMCP, Context
from config import DB_CONFIG

mcp = FastMCP("mssql")

# Database configuration from config module

DEFAULT_DB_CONFIG = {
    "server": DB_CONFIG["server"],
    "port": str(DB_CONFIG["port"]),
    "database": DB_CONFIG["database"],
    "user": DB_CONFIG["username"],
    "password": DB_CONFIG["password"],
    # TLS-related defaults – flip to True if you use Azure SQL etc.
    "encrypt": False,
    "trust_cert": True,
    # ms (ODBC takes seconds but we'll convert)
    "connect_timeout_ms": 30_000,
}

# Logging configuration

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
)

def _build_connection_string() -> str:
    """Assemble an ODBC connection string from env vars."""

    encrypt = bool(
        os.getenv("MSSQL_ENCRYPT")
        or ("true" if DEFAULT_DB_CONFIG["encrypt"] else "false")
    ).__str__().lower() == "true"

    trust_cert = bool(
        os.getenv("MSSQL_TRUST_SERVER_CERTIFICATE")
        or ("true" if DEFAULT_DB_CONFIG["trust_cert"] else "false")
    ).__str__().lower() == "true"

    parts = [
        "Driver={ODBC Driver 17 for SQL Server}",
        # host,port
        f"Server={os.getenv('DB_SERVER', DEFAULT_DB_CONFIG['server'])},"
        f"{os.getenv('DB_PORT', DEFAULT_DB_CONFIG['port'])}",
        f"Database={os.getenv('DB_NAME', DEFAULT_DB_CONFIG['database'])}",
        f"UID={os.getenv('DB_USER', DEFAULT_DB_CONFIG['user'])}",
        f"PWD={os.getenv('DB_PASSWORD', DEFAULT_DB_CONFIG['password'])}",
    ]

    if encrypt:
        parts.append("Encrypt=yes")
        parts.append(f"TrustServerCertificate={'yes' if trust_cert else 'no'}")
    else:
        parts.append("Encrypt=no")

    timeout_sec = int(
        os.getenv("MSSQL_CONNECT_TIMEOUT", str(DEFAULT_DB_CONFIG["connect_timeout_ms"] // 1000))
    )
    parts.append(f"Connection Timeout={timeout_sec}")

    return ";".join(parts)


@contextlib.contextmanager
def _get_connection():
    """Context manager that yields a live pyodbc connection."""

    try:
        conn = pyodbc.connect(
            _build_connection_string(),
            ansi=True,
            timeout=int(
                os.getenv(
                    "MSSQL_CONNECT_TIMEOUT",
                    str(DEFAULT_DB_CONFIG["connect_timeout_ms"] // 1000),
                )
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logging.exception("Failed to connect to SQL Server: %s", exc)
        raise
    try:
        yield conn
    finally:
        conn.close()


@mcp.tool(structured_output=False)
def list_tables():
    """List all tables in the database."""
    try:
        with _get_connection() as conn:
            logging.info("Listing all tables in database")
            cur = conn.cursor()
            cur.execute("""
                SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE
                FROM INFORMATION_SCHEMA.TABLES 
                WHERE TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_SCHEMA, TABLE_NAME
            """)
            return [{"schema": row[0], "table": row[1], "type": row[2]} for row in cur.fetchall()]
    except Exception as exc:  # noqa: BLE001
        logging.exception("Failed to list tables: %s", exc)
        raise


@mcp.tool(structured_output=False)
def describe_table(table_name: str):
    """Get the schema of a specific table including columns, types, and constraints."""
    try:
        with _get_connection() as conn:
            logging.info("Describing table: %s", table_name)
            cur = conn.cursor()
            cur.execute("""
                SELECT 
                    c.COLUMN_NAME,
                    c.DATA_TYPE,
                    c.CHARACTER_MAXIMUM_LENGTH,
                    c.NUMERIC_PRECISION,
                    c.NUMERIC_SCALE,
                    c.IS_NULLABLE,
                    c.COLUMN_DEFAULT,
                    c.ORDINAL_POSITION
                FROM INFORMATION_SCHEMA.COLUMNS c
                WHERE c.TABLE_NAME = ?
                ORDER BY c.ORDINAL_POSITION
            """, table_name)
            
            columns = []
            for row in cur.fetchall():
                col_info = {
                    "name": row[0],
                    "type": row[1],
                    "max_length": row[2],
                    "precision": row[3],
                    "scale": row[4],
                    "nullable": row[5] == "YES",
                    "default": row[6],
                    "position": row[7]
                }
                columns.append(col_info)
            return {"table_name": table_name, "columns": columns}
    except Exception as exc:  # noqa: BLE001
        logging.exception("Failed to describe table %s: %s", table_name, exc)
        raise


@mcp.tool(structured_output=False)
def execute_sql(query: str):
    """Execute any SQL query (SELECT, INSERT, UPDATE, DELETE, etc.)."""
    try:
        with _get_connection() as conn:
            logging.info("Executing SQL query: %s", query)
            cur = conn.cursor()
            
            # Determine query type
            query_type = query.strip().split()[0].upper()
            
            if query_type == "SELECT":
                cur.execute(query)
                columns = [c[0] for c in cur.description]
                rows = [dict(zip(columns, [str(val) if val is not None else None for val in row])) 
                       for row in cur.fetchall()]
                return {
                    "type": "select",
                    "columns": columns,
                    "rows": rows,
                    "row_count": len(rows)
                }
            else:
                # For non-SELECT queries
                cur.execute(query)
                conn.commit()
                return {
                    "type": query_type.lower(),
                    "rows_affected": cur.rowcount,
                    "message": f"{query_type} executed successfully"
                }
    except Exception as exc:  # noqa: BLE001
        logging.exception("SQL execution failed: %s", exc)
        raise


if __name__ == "__main__":
    # Make it easy to launch manually in a terminal
    logging.info("🗄️  MSSQL MCP server starting – press Ctrl-C to stop …")
    try:
        mcp.run()
    except KeyboardInterrupt:
        logging.info("Server stopped by user.") 