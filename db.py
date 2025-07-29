import streamlit as st
import psycopg2
import pandas as pd

# Function to get a database connection
@st.cache_resource
def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=st.secrets["postgres"]["host"],
            port=st.secrets["postgres"]["port"],
            dbname=st.secrets["postgres"]["dbname"],
            user=st.secrets["postgres"]["user"],
            password=st.secrets["postgres"]["password"],
        )
        return conn
    except Exception as e:
        st.error(f"Error connecting to the database: {e}")
        return None

# Function to execute a query
def execute_query(query, params=None, fetch=None):
    conn = get_db_connection()
    if conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            conn.commit()
            if fetch == "one":
                return cur.fetchone()
            elif fetch == "all":
                return cur.fetchall()

# Function to create tables
def create_tables():
    commands = (
        """
        CREATE TABLE IF NOT EXISTS "Teams" (
            "TeamName" VARCHAR(255) PRIMARY KEY,
            "Description" TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS "Participants_list" (
            id SERIAL PRIMARY KEY,
            "Name" VARCHAR(255),
            "Email" VARCHAR(255) UNIQUE,
            "Preferred Name" VARCHAR(255),
            "Experience Level" VARCHAR(255),
            "Have GenAI Experience?" BOOLEAN,
            "Background" TEXT,
            "Why do you want to join?" TEXT,
            "What are your goals?" TEXT,
            "Role Preference 1" VARCHAR(255),
            "Role Preference 2" VARCHAR(255),
            "Skills for Role" TEXT,
            "Can participate daily?" BOOLEAN,
            "Best Time to Meet" VARCHAR(255),
            "Has computer & internet?" BOOLEAN,
            "Comfortable with Tools" TEXT,
            "Other Tools Known" TEXT,
            "Anything else?" TEXT,
            "Willing to mentor future cohorts?" BOOLEAN,
            "Status" VARCHAR(255),
            "Team" VARCHAR(255),
            "PasswordHash" VARCHAR(255)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS "Projects" (
            id SERIAL PRIMARY KEY,
            "ProjectName" VARCHAR(255) UNIQUE,
            "ProjectInfo" TEXT,
            "AssignedTeam" VARCHAR(255),
            "CreatedAt" TIMESTAMP,
            "CurrentPhase" VARCHAR(255),
            "Progress" INTEGER
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS "Updates" (
            "UpdateID" VARCHAR(255) PRIMARY KEY,
            "Timestamp" TIMESTAMP,
            "Team" VARCHAR(255),
            "Email" VARCHAR(255),
            "Update" TEXT,
            "Phase" VARCHAR(255)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS "Comments" (
            id SERIAL PRIMARY KEY,
            "UpdateID" VARCHAR(255),
            "Timestamp" TIMESTAMP,
            "Email" VARCHAR(255),
            "Comment" TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS "Likes" (
            id SERIAL PRIMARY KEY,
            "UpdateID" VARCHAR(255),
            "Email" VARCHAR(255),
            UNIQUE ("UpdateID", "Email")
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS "ProjectProgress" (
            id SERIAL PRIMARY KEY,
            "ProjectName" VARCHAR(255),
            "Phase" VARCHAR(255),
            "Status" VARCHAR(255),
            "StartDate" DATE,
            "EndDate" DATE,
            "Comments" TEXT
        )
        """,
        """
        ALTER TABLE "Participants_list" ADD CONSTRAINT fk_team FOREIGN KEY ("Team") REFERENCES "Teams"("TeamName") ON DELETE SET NULL;
        """,
        """
        ALTER TABLE "Projects" ADD CONSTRAINT fk_assigned_team FOREIGN KEY ("AssignedTeam") REFERENCES "Teams"("TeamName") ON DELETE SET NULL;
        """
    )
    for command in commands:
        try:
            execute_query(command)
        except Exception as e:
            if "already exists" in str(e) or "multiple primary keys" in str(e):
                conn = get_db_connection()
                conn.rollback()
            else:
                raise e

if __name__ == "__main__":
    create_tables()
    st.success("Database tables created successfully.")
