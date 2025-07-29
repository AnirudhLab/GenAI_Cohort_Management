import streamlit as st
import pandas as pd
from app import get_sheet, get_cached_sheet_data
from db import execute_query, create_tables

def migrate_teams():
    teams_sheet = get_sheet("Teams")
    teams_data = get_cached_sheet_data("Teams", teams_sheet)
    if teams_data:
        for team in teams_data:
            execute_query(
                'INSERT INTO "Teams" ("TeamName", "Description") VALUES (%s, %s) ON CONFLICT ("TeamName") DO NOTHING',
                (team["TeamName"], team["Description"]),
            )
    st.success("Teams data migrated.")

def migrate_participants():
    participants_sheet = get_sheet("Participants_list")
    participants_data = get_cached_sheet_data("Participants_list", participants_sheet)
    if participants_data:
        for p in participants_data:
            # Handle boolean values
            genai_exp = p.get("Have GenAI Experience?", "FALSE").upper() == "TRUE"
            can_participate = p.get("Can participate daily?", "FALSE").upper() == "TRUE"
            has_computer = p.get("Has computer & internet?", "FALSE").upper() == "TRUE"
            will_mentor = p.get("Willing to mentor future cohorts?", "FALSE").upper() == "TRUE"

            execute_query(
                """
                INSERT INTO "Participants_list" (
                    "Name", "Email", "Preferred Name", "Experience Level", "Have GenAI Experience?",
                    "Background", "Why do you want to join?", "What are your goals?", "Role Preference 1",
                    "Role Preference 2", "Skills for Role", "Can participate daily?", "Best Time to Meet",
                    "Has computer & internet?", "Comfortable with Tools", "Other Tools Known", "Anything else?",
                    "Willing to mentor future cohorts?", "Status", "Team", "PasswordHash"
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT ("Email") DO NOTHING
                """,
                (
                    p.get("Name"), p.get("Email"), p.get("Preferred Name"), p.get("Experience Level"), genai_exp,
                    p.get("Background"), p.get("Why do you want to join?"), p.get("What are your goals?"),
                    p.get("Role Preference 1"), p.get("Role Preference 2"), p.get("Skills for Role"),
                    can_participate, p.get("Best Time to Meet"), has_computer, p.get("Comfortable with Tools"),
                    p.get("Other Tools Known"), p.get("Anything else?"), will_mentor, p.get("Status"),
                    p.get("Team"), p.get("PasswordHash")
                ),
            )
    st.success("Participants data migrated.")

def migrate_projects():
    projects_sheet = get_sheet("Projects")
    projects_data = get_cached_sheet_data("Projects", projects_sheet)
    if projects_data:
        for p in projects_data:
            execute_query(
                """
                INSERT INTO "Projects" (
                    "ProjectName", "ProjectInfo", "AssignedTeam", "CreatedAt", "CurrentPhase", "Progress"
                ) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT ("ProjectName") DO NOTHING
                """,
                (
                    p["ProjectName"], p.get("ProjectInfo"), p.get("AssignedTeam"),
                    pd.to_datetime(p.get("CreatedAt")), p.get("CurrentPhase"), int(p.get("Progress", 0))
                ),
            )
    st.success("Projects data migrated.")

def migrate_updates():
    updates_sheet = get_sheet("Updates")
    updates_data = get_cached_sheet_data("Updates", updates_sheet)
    if updates_data:
        for u in updates_data:
            execute_query(
                """
                INSERT INTO "Updates" ("UpdateID", "Timestamp", "Team", "Email", "Update", "Phase")
                VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT ("UpdateID") DO NOTHING
                """,
                (
                    u["UpdateID"], pd.to_datetime(u["Timestamp"]), u["Team"], u["Email"], u["Update"], u.get("Phase")
                ),
            )
    st.success("Updates data migrated.")

def migrate_comments():
    comments_sheet = get_sheet("Comments")
    comments_data = get_cached_sheet_data("Comments", comments_sheet)
    if comments_data:
        for c in comments_data:
            execute_query(
                """
                INSERT INTO "Comments" ("UpdateID", "Timestamp", "Email", "Comment")
                VALUES (%s, %s, %s, %s)
                """,
                (c["UpdateID"], pd.to_datetime(c["Timestamp"]), c["Email"], c["Comment"]),
            )
    st.success("Comments data migrated.")

def migrate_likes():
    likes_sheet = get_sheet("Likes")
    likes_data = get_cached_sheet_data("Likes", likes_sheet)
    if likes_data:
        for like in likes_data:
            execute_query(
                'INSERT INTO "Likes" ("UpdateID", "Email") VALUES (%s, %s) ON CONFLICT ("UpdateID", "Email") DO NOTHING',
                (like["UpdateID"], like["Email"]),
            )
    st.success("Likes data migrated.")

def migrate_project_progress():
    progress_sheet = get_sheet("ProjectProgress")
    progress_data = get_cached_sheet_data("ProjectProgress", progress_sheet)
    if progress_data:
        for p in progress_data:
            execute_query(
                """
                INSERT INTO "ProjectProgress" ("ProjectName", "Phase", "Status", "StartDate", "EndDate", "Comments")
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    p["ProjectName"], p["Phase"], p["Status"],
                    pd.to_datetime(p["StartDate"]).date() if p.get("StartDate") else None,
                    pd.to_datetime(p["EndDate"]).date() if p.get("EndDate") else None,
                    p.get("Comments")
                ),
            )
    st.success("Project progress data migrated.")


def main():
    st.title("Data Migration from Google Sheets to PostgreSQL")

    run_migration = st.query_params.get("run_migration")

    if run_migration == "true" or st.button("Start Migration"):
        with st.spinner("Creating tables..."):
            create_tables()
        st.success("Tables created successfully.")

        with st.spinner("Migrating data..."):
            migrate_teams()
            migrate_participants()
            migrate_projects()
            migrate_updates()
            migrate_comments()
            migrate_likes()
            migrate_project_progress()

        st.balloons()
        st.success("All data migrated successfully!")
        st.query_params.clear()

if __name__ == "__main__":
    main()
