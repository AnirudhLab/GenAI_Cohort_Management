import pytest
from unittest.mock import MagicMock, patch

# Mock streamlit before importing db
st = MagicMock()
# We need to mock psycopg2 as we don't want to connect to a real database
psycopg2 = MagicMock()

@patch('db.psycopg2')
@patch('db.st')
def test_get_db_connection(mock_st, mock_psycopg2):
    # a mock for st.secrets
    mock_st.secrets = {
        "postgres": {
            "host": "localhost",
            "port": "5432",
            "dbname": "testdb",
            "user": "",
            "password": ""
        }
    }

    from db import get_db_connection

    get_db_connection()

    mock_psycopg2.connect.assert_called_with(
        host="localhost",
        port="5432",
        dbname="testdb",
        user="testuser",
        password="testpassword"
    )

@patch('db.get_db_connection')
def test_execute_query(mock_get_db_connection):
    from db import execute_query

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_get_db_connection.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    query = "SELECT * FROM test"
    params = (1, "test")

    execute_query(query, params, fetch="all")

    mock_cursor.execute.assert_called_with(query, params)
    mock_conn.commit.assert_called()
    mock_cursor.fetchall.assert_called()

@patch('db.execute_query')
def test_create_tables(mock_execute_query):
    from db import create_tables

    create_tables()

    assert mock_execute_query.call_count == 9
