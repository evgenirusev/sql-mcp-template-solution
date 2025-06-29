"""Configuration for the SQL AI agent."""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configuration from environment variables

# OpenAI Configuration
API_KEY = os.getenv("OPENAI_API_KEY")

if not API_KEY:
    raise SystemExit(
        "OpenAI API key missing – please set the OPENAI_API_KEY environment "
        "variable in your .env file or system environment."
    )

# Performance settings
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
MAX_CONVERSATION_HISTORY = int(os.getenv("MAX_CONVERSATION_HISTORY", "50"))

# Database Configuration
DB_CONFIG = {
    "server": os.getenv("DB_SERVER", "localhost"),
    "database": os.getenv("DB_NAME", "SalesAnalytics"),
    "username": os.getenv("DB_USER", "sa"),
    "password": os.getenv("DB_PASSWORD"),
    "port": int(os.getenv("DB_PORT", "1433")),
    "driver": os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
}

if not DB_CONFIG["password"]:
    raise SystemExit(
        "Database password missing – please set the DB_PASSWORD environment "
        "variable in your .env file or system environment."
    )

# OpenAI function specifications - dynamically loaded from MCP server
# This will be populated at runtime by the MCP client
FUNCTIONS_SPEC = []

SYSTEM_PROMPT = """You are an expert data assistant with access to a SQL Server database.

Available tools:
1. list_tables() - See all tables in the database
2. describe_table(table_name) - Examine table schema and columns
3. execute_sql(query) - Run any SQL query

Best practices:
- Always explore the database structure first if unsure about table names or columns
- Use describe_table before writing complex queries to understand the schema
- Write efficient queries with appropriate JOINs and WHERE clauses
- For analysis tasks, break down complex requirements into multiple queries
- Present results clearly with explanations of what the data shows

The database name is 'SalesAnalytics'. You can execute both read and write operations.""" 