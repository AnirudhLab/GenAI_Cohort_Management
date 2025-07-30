import streamlit as st
import pandas as pd
from werkzeug.security import check_password_hash, generate_password_hash
import yagmail
import os
from datetime import datetime, timedelta
import requests
import json
from db import execute_query

# Initialize session state
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_role = None
    st.session_state.user_email = None
    st.session_state.sheet_data_cache = {}
    st.session_state.last_sheet_refresh = {}

def validate_secrets():
    """Validate all required secrets are present"""
    required_configs = {
        "admin": ["email", "password"],
        "gmail": ["sender_email", "app_password"],
        "postgres": ["host", "port", "dbname", "user", "password"]
    }
    
    missing = []
    for section, keys in required_configs.items():
        if section not in st.secrets:
            missing.append(f"Missing section: {section}")
            continue
        for key in keys:
            if key not in st.secrets[section]:
                missing.append(f"Missing key in {section}: {key}")
    
    return missing

def check_admin_login(email, password):
    """Check admin credentials from secrets.toml"""
    try:
        if "admin" not in st.secrets:
            st.error("Admin configuration missing in secrets.toml")
            return False
            
        admin_config = st.secrets["admin"]
        if "email" not in admin_config or "password" not in admin_config:
            st.error("Admin email or password missing in secrets.toml")
            return False
            
        return email == admin_config["email"] and password == admin_config["password"]
        
    except Exception as e:
        st.error(f"Error checking admin credentials: {str(e)}")
        return False

# --- 1. CONFIGURATION & SETUP ---

# Page Configuration
st.set_page_config(page_title="GenAI Cohort Portal", layout="wide")

# Page Configuration
st.set_page_config(page_title="GenAI Cohort Portal", layout="wide")

def clear_cache():
    """Clears the sheet data cache."""
    st.session_state.sheet_data_cache = {}
    st.session_state.last_sheet_refresh = {}

def send_email_notification(to_email, subject, message_text):
    """Send email using Gmail via yagmail"""
    try:
        # Check Gmail configuration
        if "gmail" not in st.secrets:
            st.error("Gmail configuration not found in secrets.toml")
            return False
            
        gmail_config = st.secrets["gmail"]
        sender_email = gmail_config.get("sender_email")
        app_password = gmail_config.get("app_password")
        
        if not sender_email or not app_password:
            st.error("Gmail sender email or app password not configured")
            return False
            
        try:
            # Initialize yagmail SMTP with UTF-8 encoding
            yag = yagmail.SMTP({sender_email: "GenAI Cohort"}, app_password)
            
            # Send the email
            yag.send(
                to=to_email,
                subject=subject,
                contents=message_text
            )
            
            st.success(f"Email sent successfully to {to_email}")
            return True
            
        except Exception as e:
            st.error(f"Failed to send email: {str(e)}")
            return False
            
    except Exception as e:
        st.error(f"Failed to prepare email: {str(e)}")
        return False

def notify_participant(email, participant_name, team_name, notification_type="team_assignment", project_name=None):
    """Send notification to participant"""
    try:
        # Clean input strings - handle encoding explicitly
        def clean_string(s):
            if not s:
                return ""
            # Convert to string and normalize whitespace
            s = str(s).strip()
            # Remove any non-breaking spaces and normalize
            s = s.replace('\xa0', ' ').replace('\u00a0', ' ')
            return ' '.join(s.split())
        
        participant_name = clean_string(participant_name)
        team_name = clean_string(team_name)
        project_name = clean_string(project_name) if project_name else None
        
        # Prepare email content based on notification type
        if notification_type == "team_assignment":
            subject = "Welcome to GenAI Cohort - Team Assignment"
            message = f"""Dear {participant_name},

Welcome to the GenAI Cohort! We're excited to have you on board.

You have been assigned to team: {team_name}

To get started:
1. Visit our portal
2. Click "Sign Up"
3. Use your email: {email}
4. Create your password
5. Log in to view your team and project details

Best regards,
The GenAI Cohort Admin Team"""

        elif notification_type == "project_assignment":
            if not project_name:
                st.warning("Project name is required for project assignment notifications")
                return False
                
            subject = f"New Project Assignment - {project_name}"
            message = f"""Dear {participant_name},

A new project has been assigned to your team ({team_name}).

Project: {project_name}

Please log in to the portal to:
- View project details
- Collaborate with your team
- Submit progress updates

Best regards,
The GenAI Cohort Admin Team"""
        
        elif notification_type == "password_reset":
            subject = "Password Reset Successful"
            message = f"""Dear {participant_name},

Your password has been reset successfully.

Please log in to the portal using your new password.

Best regards,
The GenAI Cohort Admin Team"""

        else:
            st.warning(f"Unknown notification type: {notification_type}")
            return False
            
        # Send email
        success = send_email_notification(email, subject, message)
        
        if success:
            st.success(f"Successfully sent {notification_type} notification to {participant_name}")
        else:
            st.error(f"Failed to send {notification_type} notification to {participant_name}")
        
        return success
        
    except Exception as e:
        st.error(f"Failed to prepare notification for {participant_name}: {str(e)}")
        return False

# --- 2. ADMIN VIEW ---
def create_participant(name, email, team):
    """Create a new participant in the database."""
    try:
        # Check if participant email already exists
        existing_participant = execute_query('SELECT "Email" FROM "Participants_list" WHERE "Email" = %s', (email,), fetch="one")
        if existing_participant:
            st.error("A participant with this email already exists!")
            return False
        else:
            execute_query(
                'INSERT INTO "Participants_list" ("Name", "Email", "Team", "Status") VALUES (%s, %s, %s, %s)',
                (name, email, team if team else None, "Pending")
            )
            st.success(f"Participant '{name}' created successfully!")
            clear_cache()
            st.rerun()
            return True
    except Exception as e:
        st.error(f"Failed to create participant: {str(e)}")
        return False

def show_admin_view():
    st.title("Admin Dashboard")
    
    # Create tabs for different admin functions
    team_tab, project_tab, progress_tab, updates_tab, password_tab = st.tabs([
        "Team Management",
        "Project Management",
        "Project Progress",
        "Team Updates",
        "Password Management"
    ])
    
    # Initialize participants_df at a higher scope
    participants_df = None
    available_teams = []
    
    try:
        # Load participants first
        participants_data = execute_query('SELECT * FROM "Participants_list"', fetch="all")
        if participants_data:
            participants_df = pd.DataFrame(participants_data, columns=["id", "Name", "Email", "Preferred Name", "Experience Level", "Have GenAI Experience?", "Background", "Why do you want to join?", "What are your goals?", "Role Preference 1", "Role Preference 2", "Skills for Role", "Can participate daily?", "Best Time to Meet", "Has computer & internet?", "Comfortable with Tools", "Other Tools Known", "Anything else?", "Willing to mentor future cohorts?", "Status", "Team", "PasswordHash"])
            
            # Data cleaning
            participants_df = participants_df.fillna("")
            participants_df = participants_df[participants_df["Email"].astype(str).str.strip() != ""]
            participants_df["Display Name"] = participants_df["Preferred Name"].where(participants_df["Preferred Name"].astype(str).str.strip() != "", participants_df["Name"])
            if "Team" not in participants_df.columns:
                participants_df["Team"] = ""
            participants_df["Team"] = participants_df["Team"].fillna("").astype(str)
            participants_df["Team"] = participants_df["Team"].replace({"nan": "", "None": "", "null": ""}).str.strip()
            if "PasswordHash" not in participants_df.columns:
                participants_df["PasswordHash"] = ""
        else:
            st.warning("No participant data found in the database.")
            participants_df = pd.DataFrame()

        # Load teams
        teams_data = execute_query('SELECT "TeamName", "Description" FROM "Teams"', fetch="all")
        teams_df = pd.DataFrame(teams_data, columns=["TeamName", "Description"]) if teams_data else pd.DataFrame(columns=["TeamName", "Description"])
        available_teams = teams_df["TeamName"].tolist()

    except Exception as e:
        st.error(f"Error loading data from database: {str(e)}")
        return
    
    with team_tab:
        st.subheader("Team Management")
        
        # Team Management Section
        st.write("### Team Management")
        
        # Create columns for team actions
        col1, col2 = st.columns(2)
        
        with col1:
            # Create New Team
            with st.form("create_team"):
                st.write("#### Create New Team")
                new_team_name = st.text_input("Team Name")
                team_description = st.text_area("Team Description")
                submit_team = st.form_submit_button("Create Team")
                
                if submit_team:
                    if not new_team_name or not team_description:
                        st.error("Team name and description are required!")
                    else:
                        try:
                            # Check if team name already exists
                            if not teams_df.empty and new_team_name in teams_df["TeamName"].values:
                                st.error("A team with this name already exists!")
                            else:
                                execute_query('INSERT INTO "Teams" ("TeamName", "Description") VALUES (%s, %s)', (new_team_name, team_description))
                                st.success(f"Team '{new_team_name}' created successfully!")
                                clear_cache()
                                st.rerun()
                        except Exception as e:
                            st.error(f"Failed to create team: {str(e)}")
        
        with col2:
            # Delete Team
            if available_teams:
                st.write("#### Delete Team")
                team_to_delete = st.selectbox(
                    "Select team to delete:",
                    options=available_teams,
                    help="Warning: Deleting a team will remove all participant assignments for that team"
                )
                
                if st.button("Delete Team", type="primary"):
                    if st.checkbox("Confirm deletion of " + team_to_delete):
                        try:
                            # Remove team assignments from participants
                            execute_query('UPDATE "Participants_list" SET "Team" = NULL WHERE "Team" = %s', (team_to_delete,))
                            
                            # Delete team from Teams table
                            execute_query('DELETE FROM "Teams" WHERE "TeamName" = %s', (team_to_delete,))
                            
                            st.success(f"Team '{team_to_delete}' deleted successfully!")
                            clear_cache()
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to delete team: {str(e)}")

        st.write("### Create New Participant")
        with st.form("create_participant"):
            st.write("#### Create New Participant")
            new_participant_name = st.text_input("Participant Name")
            new_participant_email = st.text_input("Participant Email")
            assigned_team = st.selectbox("Assign to Team", [""] + available_teams)
            submit_participant = st.form_submit_button("Create Participant")

            if submit_participant:
                if not new_participant_name or not new_participant_email:
                    st.error("Participant name and email are required!")
                else:
                    create_participant(new_participant_name, new_participant_email, assigned_team)
        
        # Display current team assignments
        st.write("### Current Team Assignments")
        
        if participants_df is None:
            st.error("No participant data available. Please check the connection to Google Sheets.")
            return
            
        if not available_teams:
            st.warning("No teams created yet. Please create teams first.")
            
            # Still show all participants
            st.write("#### All Participants (Unassigned)")
            display_columns = ["Display Name", "Email", "Background", "Role Preference 1"]
            st.dataframe(participants_df[display_columns], hide_index=True)
        else:
            # Display teams in columns
            cols = st.columns(len(available_teams) + 1)  # +1 for unassigned
            
            # Display each team's members
            for i, team_name in enumerate(available_teams):
                with cols[i]:
                    st.write(f"#### {team_name}")
                    team_df = participants_df[participants_df["Team"] == team_name][["Display Name", "Email", "Background", "Role Preference 1"]]
                    if not team_df.empty:
                        st.dataframe(team_df, hide_index=True)
                    else:
                        st.info("No members yet")
            
            # Display unassigned participants
            with cols[-1]:
                st.write("#### Unassigned")
                unassigned_df = participants_df[participants_df["Team"].str.strip() == ""][["Display Name", "Email", "Background", "Role Preference 1"]]
                if not unassigned_df.empty:
                    st.dataframe(unassigned_df, hide_index=True)
                else:
                    st.success("All participants assigned!")
        
        # Team Assignment Section
        st.write("### Assign Participants to Teams")
        
        if not available_teams:
            st.warning("Please create teams before assigning participants.")
        else:
            st.info("Select participants and their teams below.")
            
            # Get unassigned participants
            unassigned_participants = participants_df[
                (participants_df["Team"].str.strip() == "") | 
                (participants_df["Team"].isna()) | 
                (participants_df["Team"].str.lower().isin(["nan", "none", "null"]))
            ]
            
            # Create lists of names for selection
            unassigned_names = [
                name for name in unassigned_participants["Display Name"].tolist() 
                if isinstance(name, str) and name.strip()
            ]
            
            if not unassigned_names:
                st.success("All participants have been assigned to teams!")
            else:
                st.write(f"Number of participants to assign: {len(unassigned_names)}")
                
                # Create columns for team assignment
                col1, col2 = st.columns(2)
                
                with col1:
                    selected_participants = st.multiselect(
                        "Select participants:",
                        options=sorted(unassigned_names),
                        help="Choose one or more participants to assign to a team"
                    )
                
                with col2:
                    selected_team = st.selectbox(
                        "Assign to team:",
                        options=[""] + available_teams,
                        help="Choose the team to assign the selected participants to"
                    )

                if st.button("Assign Teams", 
                           type="primary", 
                           disabled=not (selected_participants and selected_team)):
                    
                    with st.spinner("Assigning teams..."):
                        try:
                            notifications_sent = []  # Track successful notifications
                            failed_notifications = []  # Track failed notifications
                            
                            # Update database with new team assignments
                            for participant_name in selected_participants:
                                participant_row = participants_df[participants_df["Display Name"] == participant_name].iloc[0]
                                participant_email = participant_row["Email"]
                                
                                execute_query('UPDATE "Participants_list" SET "Team" = %s WHERE "Email" = %s', (selected_team, participant_email))
                                
                                # Try to send notification
                                if notify_participant(participant_email, participant_name, selected_team):
                                    notifications_sent.append(participant_name)
                                else:
                                    failed_notifications.append(participant_name)
                            
                            # Show success message for team assignment
                            st.success(f"Successfully assigned {len(selected_participants)} participants to {selected_team}!")
                            
                            # Show notification status
                            if notifications_sent:
                                st.success(f"Sent notifications to: {', '.join(notifications_sent)}")
                            if failed_notifications:
                                st.warning(f"Failed to send notifications to: {', '.join(failed_notifications)}")
                            
                            clear_cache()
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to update team assignments: {str(e)}")
                            if "notifications_sent" in locals():
                                # Still show any successful notifications
                                if notifications_sent:
                                    st.success(f"Sent notifications to: {', '.join(notifications_sent)}")
                                if failed_notifications:
                                    st.warning(f"Failed to send notifications to: {', '.join(failed_notifications)}")
    
    with project_tab:
        if participants_df is not None:
            show_project_tab(participants_df, available_teams)
        else:
            st.error("Cannot show project management until participant data is loaded.")
    
    with progress_tab:
        show_project_progress_dashboard()
    
    with updates_tab:
        show_updates_dashboard(st.session_state.user_email, "admin")
    
    with password_tab:
        st.subheader("Password Management")
        
        try:
            if participants_df is None:
                st.error("Cannot load participant data. Please check your connection.")
                return
                
            # Show participant list with password status
            st.write("### Participant Passwords")
            
            # Create a status column
            participants_df["Password Status"] = participants_df["PasswordHash"].apply(
                lambda x: "✅ Set" if x and str(x).strip() else "❌ Not Set"
            )
            
            # Display participant list
            st.dataframe(
                participants_df[["Name", "Email", "Password Status"]],
                hide_index=True
            )
            
            # Password reset section
            st.write("### Reset Participant Password")
            
            # Select participant
            selected_email = st.selectbox(
                "Select Participant",
                options=participants_df["Email"].tolist(),
                format_func=lambda x: f"{participants_df[participants_df['Email']==x]['Name'].iloc[0]} ({x})"
            )
            
            # Password reset form
            with st.form("reset_password"):
                new_password = st.text_input("New Password", type="password")
                confirm_password = st.text_input("Confirm Password", type="password")
                send_notification = st.checkbox("Send email notification", value=True)
                
                if st.form_submit_button("Reset Password"):
                    if not new_password or not confirm_password:
                        st.error("Please enter and confirm the new password.")
                    elif new_password != confirm_password:
                        st.error("Passwords do not match.")
                    elif len(new_password) < 6:
                        st.error("Password must be at least 6 characters long.")
                    else:
                        if reset_participant_password(selected_email, new_password):
                            st.success(f"Password reset successful for {selected_email}")
                            
                            # Send notification if requested
                            if send_notification:
                                try:
                                    participant_name = participants_df[
                                        participants_df["Email"] == selected_email
                                    ]["Name"].iloc[0]
                                    team_name = participants_df[
                                        participants_df["Email"] == selected_email
                                    ]["Team"].iloc[0]
                                    
                                    notify_participant(
                                        selected_email,
                                        participant_name,
                                        team_name,
                                        "password_reset"
                                    )
                                except Exception as e:
                                    st.warning(f"Password reset successful but failed to send notification: {str(e)}")
                            
                            # Clear cache and refresh
                            clear_cache()
                            st.rerun()
                        else:
                            st.error("Failed to reset password. Please try again.")
            
            # Add help text
            st.markdown("""
            ---
            ### Password Management Help
            - Participants can change their own passwords after logging in
            - Passwords must be at least 6 characters long
            - Use the reset function if a participant forgets their password
            - Email notifications will be sent when passwords are reset
            """)
            
        except Exception as e:
            st.error(f"Error in password management: {str(e)}")
            return
        else:
            st.warning("Password management is restricted to super administrators only.")

def show_project_tab(participants_df, available_teams):
    st.subheader("Project Management")
    
    # Create New Project Section
    st.write("### Create New Project")
    with st.form("create_project"):
        project_name = st.text_input("Project Name")
        project_description = st.text_area("Project Description")
        assigned_team = st.selectbox(
            "Assign Team",
            options=available_teams,
            help="Select the team to assign this project to"
        )
        send_notifications = st.checkbox("Send notifications to team members", value=True)
        
        if st.form_submit_button("Create Project"):
            if not project_name or not project_description or not assigned_team:
                st.error("All fields are required!")
            else:
                try:
                    # Add project to Projects table
                    timestamp = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
                    execute_query(
                        'INSERT INTO "Projects" ("ProjectName", "ProjectInfo", "AssignedTeam", "CreatedAt", "CurrentPhase", "Progress") VALUES (%s, %s, %s, %s, %s, %s)',
                        (project_name, project_description, assigned_team, timestamp, "Requirements", 0)
                    )
                    st.success(f"Project '{project_name}' created successfully!")
                    
                    # Send notifications if requested
                    if send_notifications:
                        # Get team members
                        team_members = participants_df[participants_df["Team"] == assigned_team]
                        
                        if team_members.empty:
                            st.warning(f"No members found in team {assigned_team}")
                        else:
                            notifications_sent = []
                            failed_notifications = []
                            
                            with st.spinner(f"Sending notifications to {len(team_members)} team members..."):
                                for _, member in team_members.iterrows():
                                    if notify_participant(
                                        member["Email"],
                                        member["Display Name"],
                                        assigned_team,
                                        notification_type="project_assignment",
                                        project_name=project_name
                                    ):
                                        notifications_sent.append(member["Display Name"])
                                    else:
                                        failed_notifications.append(member["Display Name"])
                            
                            if notifications_sent:
                                st.success(f"Successfully notified: {', '.join(notifications_sent)}")
                            if failed_notifications:
                                st.error(f"Failed to notify: {', '.join(failed_notifications)}")
                    
                    clear_cache()
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"Failed to create project: {str(e)}")
    
    # Display existing projects
    st.write("### Existing Projects")
    try:
        projects_data = execute_query('SELECT "ProjectName", "ProjectInfo", "AssignedTeam", "CreatedAt", "CurrentPhase", "Progress" FROM "Projects"', fetch="all")
        
        if not projects_data:
            st.info("No projects created yet.")
            return
            
        projects_df = pd.DataFrame(projects_data, columns=["Project Name", "Description", "Assigned Team", "Created At", "Current Phase", "Progress"])
        
        # Group projects by team
        for team in available_teams:
            team_projects = projects_df[projects_df["Assigned Team"] == team]
            if not team_projects.empty:
                st.write(f"#### {team} Projects")
                
                for idx, project in team_projects.iterrows():
                    with st.expander(f"{project['Project Name']} ({project['Created At']})"):
                        st.write("**Description:**")
                        st.write(project["Description"])
                        
                        # Show project progress
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write("**Current Phase:**", project["Current Phase"])
                        with col2:
                            st.write("**Progress:**", f"{project['Progress']}%")
                        
                        st.write("---")
                        
                        # Show team members
                        team_members = participants_df[participants_df["Team"] == team]
                        st.write("**Team Members:**")
                        st.dataframe(
                            team_members[["Display Name", "Email", "Background", "Role Preference 1"]],
                            hide_index=True
                        )
                        
                        col1, col2 = st.columns(2)
                        
                        # Add notify button
                        with col1:
                            if st.button("Send Notification", key=f"notify_{project['Project Name']}"):
                                notifications_sent = []
                                failed_notifications = []
                                
                                for _, member in team_members.iterrows():
                                    if notify_participant(
                                        member["Email"],
                                        member["Display Name"],
                                        team,
                                        notification_type="project_assignment",
                                        project_name=project["Project Name"]
                                    ):
                                        notifications_sent.append(member["Display Name"])
                                    else:
                                        failed_notifications.append(member["Display Name"])
                                
                                if notifications_sent:
                                    st.success(f"Sent notifications to: {', '.join(notifications_sent)}")
                                if failed_notifications:
                                    st.warning(f"Failed to send notifications to: {', '.join(failed_notifications)}")
                        
                        # Add delete button
                        with col2:
                            if st.button("Delete Project", key=f"delete_{project['Project Name']}", type="primary"):
                                if st.checkbox(f"Confirm deletion of project: {project['Project Name']}", key=f"confirm_{project['Project Name']}"):
                                    try:
                                        execute_query('DELETE FROM "Projects" WHERE "ProjectName" = %s', (project['Project Name'],))
                                        st.success(f"Project '{project['Project Name']}' deleted successfully!")
                                        clear_cache()
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Failed to delete project: {str(e)}")
                
                st.write("")  # Add space between teams
                
    except Exception as e:
        st.error(f"Error loading projects: {str(e)}")
        return

def show_updates_dashboard(user_email, user_role):
    """Show team updates dashboard with likes and comments"""
    st.title("Team Updates Dashboard")
    
    try:
        # Load all required data
        updates_data = execute_query('SELECT "UpdateID", "Timestamp", "Team", "Email", "Update", "Phase" FROM "Updates"', fetch="all")
        comments_data = execute_query('SELECT "UpdateID", "Timestamp", "Email", "Comment" FROM "Comments"', fetch="all")
        likes_data = execute_query('SELECT "UpdateID", "Email" FROM "Likes"', fetch="all")
        
        if not updates_data:
            st.info("No updates posted yet.")
            return
            
        # Convert to DataFrames
        updates_df = pd.DataFrame(updates_data, columns=["UpdateID", "Timestamp", "Team", "Email", "Update", "Phase"])
        comments_df = pd.DataFrame(comments_data, columns=["UpdateID", "Timestamp", "Email", "Comment"]) if comments_data else pd.DataFrame(columns=["UpdateID", "Timestamp", "Email", "Comment"])
        likes_df = pd.DataFrame(likes_data, columns=["UpdateID", "Email"]) if likes_data else pd.DataFrame(columns=["UpdateID", "Email"])
        
        # Add filter for teams
        teams = sorted(updates_df["Team"].unique())
        selected_team = st.selectbox("Filter by Team", ["All Teams"] + list(teams))
        
        # Filter updates by team if selected
        if selected_team != "All Teams":
            updates_df = updates_df[updates_df["Team"] == selected_team]
        
        # Sort updates by timestamp (newest first)
        updates_df["Timestamp"] = pd.to_datetime(updates_df["Timestamp"])
        updates_df = updates_df.sort_values("Timestamp", ascending=False)
        
        # Display updates
        for _, update in updates_df.iterrows():
            with st.container():
                st.markdown("---")
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    st.write(f"**Team:** {update['Team']}")
                    st.write(f"**Update by:** {update['Email']}")
                    st.write(f"**Posted on:** {update['Timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
                    if 'Phase' in update and update['Phase']:
                        st.write(f"**Phase:** {update['Phase']}")
                
                with col2:
                    # Like button
                    update_likes = likes_df[likes_df["UpdateID"] == update["UpdateID"]]
                    like_count = len(update_likes)
                    already_liked = user_email in update_likes["Email"].values
                    
                    if st.button(
                        "👍 Unlike" if already_liked else "👍 Like",
                        key=f"like_{update['UpdateID']}"
                    ):
                        if already_liked:
                            # Remove like
                            execute_query('DELETE FROM "Likes" WHERE "UpdateID" = %s AND "Email" = %s', (update["UpdateID"], user_email))
                        else:
                            # Add like
                            execute_query('INSERT INTO "Likes" ("UpdateID", "Email") VALUES (%s, %s)', (update["UpdateID"], user_email))
                        clear_cache()
                        st.rerun()
                    
                    st.write(f"{like_count} likes")
                
                # Display the update text
                st.markdown(f"**Update:**\n{update['Update']}")
                
                # Comments section
                st.write("**Comments:**")
                update_comments = comments_df[comments_df["UpdateID"] == update["UpdateID"]]
                
                if not update_comments.empty:
                    for _, comment in update_comments.iterrows():
                        with st.container():
                            st.write(f"**{comment['Email']}** ({comment['Timestamp']}):")
                            st.write(comment["Comment"])
                
                # Add comment form
                with st.form(key=f"comment_form_{update['UpdateID']}"):
                    new_comment = st.text_area("Add a comment:", key=f"comment_{update['UpdateID']}")
                    if st.form_submit_button("Post Comment"):
                        if new_comment.strip():
                            # Add comment
                            execute_query(
                                'INSERT INTO "Comments" ("UpdateID", "Timestamp", "Email", "Comment") VALUES (%s, %s, %s, %s)',
                                (update["UpdateID"], pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"), user_email, new_comment)
                            )
                            clear_cache()
                            st.rerun()
                        else:
                            st.error("Please enter a comment before posting.")
    
    except Exception as e:
        st.error(f"Error loading updates dashboard: {str(e)}")
        return

def show_project_progress_dashboard():
    """Show project progress dashboard with SDLC tracking (admin only)"""
    st.title("Project Progress Dashboard")
    
    try:
        # Load all required data
        projects_data = execute_query('SELECT "ProjectName", "CurrentPhase", "Progress" FROM "Projects"', fetch="all")
        progress_data = execute_query('SELECT "ProjectName", "Phase", "Status", "StartDate", "EndDate", "Comments" FROM "ProjectProgress"', fetch="all")

        if not projects_data:
            st.info("No projects created yet.")
            return
            
        # Convert to DataFrames
        projects_df = pd.DataFrame(projects_data, columns=["ProjectName", "CurrentPhase", "Progress"])
        progress_df = pd.DataFrame(progress_data, columns=["ProjectName", "Phase", "Status", "StartDate", "EndDate", "Comments"]) if progress_data else pd.DataFrame(columns=["ProjectName", "Phase", "Status", "StartDate", "EndDate", "Comments"])
        
        # Select project to view/update
        project_names = projects_df["ProjectName"].unique()
        selected_project = st.selectbox("Select Project", project_names)
        
        if selected_project:
            st.write(f"### {selected_project} Progress")
            
            # Create tabs for different views
            overview_tab, update_tab = st.tabs(["Progress Overview", "Update Progress"])
            
            with overview_tab:
                # Show current phase
                current_project = projects_df[projects_df["ProjectName"] == selected_project].iloc[0]
                current_phase = current_project.get("CurrentPhase", "Not Started")
                overall_progress = current_project.get("Progress", "0")
                
                # Convert progress to integer, handling empty strings and invalid values
                try:
                    progress_value = int(overall_progress)
                except (ValueError, TypeError):
                    progress_value = 0
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Current Phase", current_phase)
                with col2:
                    st.metric("Overall Progress", f"{progress_value}%")
                
                # Show phase-wise progress
                st.write("### Phase-wise Progress")
                project_progress = progress_df[progress_df["ProjectName"] == selected_project]
                
                if not project_progress.empty:
                    for phase in st.session_state.sdlc_phases:
                        phase_data = project_progress[project_progress["Phase"] == phase]
                        if not phase_data.empty:
                            with st.expander(f"{phase} ({phase_data.iloc[0]['Status']})"):
                                data = phase_data.iloc[0]
                                st.write(f"**Started:** {data['StartDate']}")
                                if data['EndDate']:
                                    st.write(f"**Completed:** {data['EndDate']}")
                                if data['Comments']:
                                    st.write(f"**Comments:** {data['Comments']}")
                else:
                    st.info("No progress data recorded yet.")
            
            with update_tab:
                st.write("### Update Project Progress")
                
                # Form to update progress
                with st.form("update_progress_form"):  # Changed form key to be unique
                    # Select phase
                    phase = st.selectbox("Select Phase", st.session_state.sdlc_phases)
                    
                    # Status
                    status = st.selectbox(
                        "Status",
                        ["Not Started", "In Progress", "Completed", "On Hold"]
                    )
                    
                    # Dates
                    col1, col2 = st.columns(2)
                    with col1:
                        start_date = st.date_input("Start Date")
                    with col2:
                        end_date = st.date_input("End Date (leave unchanged if not completed)") if status == "Completed" else None
                    
                    # Comments
                    comments = st.text_area("Comments")
                    
                    # Overall progress
                    try:
                        current_progress = int(overall_progress)
                    except (ValueError, TypeError):
                        current_progress = 0
                    
                    progress = st.slider("Overall Progress (%)", 0, 100, current_progress)
                    
                    # Add submit button
                    submitted = st.form_submit_button("Update Progress")
                    
                    if submitted:
                        try:
                            # Update project's current phase and progress in the Projects table
                            execute_query(
                                'UPDATE "Projects" SET "CurrentPhase" = %s, "Progress" = %s WHERE "ProjectName" = %s',
                                (phase, progress, selected_project)
                            )

                            # Check if a progress entry for this phase already exists
                            existing_progress = execute_query(
                                'SELECT id FROM "ProjectProgress" WHERE "ProjectName" = %s AND "Phase" = %s',
                                (selected_project, phase),
                                fetch="one"
                            )

                            if existing_progress:
                                # Update existing entry
                                execute_query(
                                    """
                                    UPDATE "ProjectProgress"
                                    SET "Status" = %s, "StartDate" = %s, "EndDate" = %s, "Comments" = %s
                                    WHERE "ProjectName" = %s AND "Phase" = %s
                                    """,
                                    (status, start_date, end_date.strftime("%Y-%m-%d") if end_date else None, comments, selected_project, phase)
                                )
                            else:
                                # Insert new entry
                                execute_query(
                                    """
                                    INSERT INTO "ProjectProgress" ("ProjectName", "Phase", "Status", "StartDate", "EndDate", "Comments")
                                    VALUES (%s, %s, %s, %s, %s, %s)
                                    """,
                                    (selected_project, phase, status, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d") if end_date else None, comments)
                                )
                            
                            st.success("Progress updated successfully!")
                            clear_cache()
                            st.rerun()
                            
                        except Exception as e:
                            st.error(f"Failed to update progress: {str(e)}")
    
    except Exception as e:
        st.error(f"Error loading progress dashboard: {str(e)}")
        return

# --- 3. PARTICIPANT VIEW ---
def show_participant_view():
    user_email = st.session_state.user_email
    
    # Create tabs for different views
    dashboard_tab, updates_tab = st.tabs(["Your Dashboard", "Team Updates"])
    
    with dashboard_tab:
        st.title("Participant Dashboard")
        
        # Add password change section in sidebar
        with st.sidebar:
            st.subheader("Change Password")
            with st.form("change_password"):
                current_password = st.text_input("Current Password", type="password")
                new_password = st.text_input("New Password", type="password")
                confirm_password = st.text_input("Confirm New Password", type="password")
                
                if st.form_submit_button("Change Password"):
                    if not current_password or not new_password or not confirm_password:
                        st.error("All fields are required.")
                    elif new_password != confirm_password:
                        st.error("New passwords do not match.")
                    elif len(new_password) < 6:
                        st.error("New password must be at least 6 characters long.")
                    else:
                        if change_participant_password(user_email, current_password, new_password):
                            st.success("Password changed successfully!")
                            st.info("Please log out and log in with your new password.")
                        else:
                            st.error("Failed to change password. Please try again.")
        
        # Fetch data
        participants_data = execute_query('SELECT * FROM "Participants_list" WHERE "Email" = %s', (user_email,), fetch="all")
        participants_df = pd.DataFrame(participants_data, columns=["id", "Name", "Email", "Preferred Name", "Experience Level", "Have GenAI Experience?", "Background", "Why do you want to join?", "What are your goals?", "Role Preference 1", "Role Preference 2", "Skills for Role", "Can participate daily?", "Best Time to Meet", "Has computer & internet?", "Comfortable with Tools", "Other Tools Known", "Anything else?", "Willing to mentor future cohorts?", "Status", "Team", "PasswordHash"])
        
        projects_data = execute_query('SELECT "ProjectName", "ProjectInfo", "AssignedTeam", "CurrentPhase", "Progress" FROM "Projects"', fetch="all")
        projects_df = pd.DataFrame(projects_data, columns=["ProjectName", "ProjectInfo", "AssignedTeam", "CurrentPhase", "Progress"]) if projects_data else pd.DataFrame(columns=["ProjectName", "ProjectInfo", "AssignedTeam", "CurrentPhase", "Progress"])
        
        # Find user's team and project
        user_info = participants_df.iloc[0]
        user_team = user_info["Team"]
        
        if not user_team:
            st.warning("You have not been assigned to a team yet. Please contact an admin.")
            return
        
        st.header(f"Your Team: {user_team}")
        project_info = projects_df[projects_df["AssignedTeam"] == user_team]
        
        if project_info.empty:
            st.info("Your team has not been assigned a project yet.")
        else:
            project = project_info.iloc[0]
            st.subheader(f"Project: {project['ProjectName']}")
            st.markdown(project["ProjectInfo"])
            
            # Show project progress if available
            if "CurrentPhase" in project and "Progress" in project:
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Current Phase", project["CurrentPhase"])
                with col2:
                    st.metric("Overall Progress", f"{project['Progress']}%")
        
        st.markdown("---")
        st.subheader("Submit Your Progress Update")
        
        with st.form("update_form", clear_on_submit=True):
            # Add phase selection if project exists
            phase = None
            if not project_info.empty and "CurrentPhase" in project:
                phase = st.selectbox("Update for Phase", st.session_state.sdlc_phases, 
                                   index=st.session_state.sdlc_phases.index(project["CurrentPhase"]))
            
            update_text = st.text_area("Enter your update here:")
            submitted = st.form_submit_button("Submit Update")
            
            if submitted and update_text:
                try:
                    # Generate a unique ID for the update
                    update_id = f"upd_{pd.Timestamp.now().strftime('%Y%m%d%H%M%S')}_{user_email}"
                    timestamp = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    # Add update to the database
                    execute_query(
                        'INSERT INTO "Updates" ("UpdateID", "Timestamp", "Team", "Email", "Update", "Phase") VALUES (%s, %s, %s, %s, %s, %s)',
                        (update_id, timestamp, user_team, user_email, update_text, phase if phase else "")
                    )
                    st.success("Your update has been submitted successfully!")
                    clear_cache()
                except Exception as e:
                    st.error(f"Failed to submit update: {str(e)}")
    
    with updates_tab:
        show_updates_dashboard(user_email, "participant")

# --- 4. MAIN APP & LOGIN LOGIC ---

def reset_participant_password(email, new_password):
    """Reset password for a participant"""
    try:
        password_hash = generate_password_hash(new_password)
        execute_query('UPDATE "Participants_list" SET "PasswordHash" = %s WHERE "Email" = %s', (password_hash, email))
        return True
    except Exception as e:
        st.error(f"Failed to reset password: {str(e)}")
        return False

def check_participant_login(email, password):
    """Check participant credentials from the database"""
    try:
        user_data = execute_query('SELECT "PasswordHash" FROM "Participants_list" WHERE "Email" = %s', (email,), fetch="one")
        
        if not user_data:
            st.error("Email not found. Please check your email or contact admin.")
            return False
        
        user_password_hash = user_data[0]
        if not user_password_hash:
            st.error("Password not set. Please contact admin to reset your password.")
            return False
        
        return check_password_hash(user_password_hash, password)
        
    except Exception as e:
        st.error(f"Error checking participant login: {str(e)}")
        return False

# Add this function for participant password change
def change_participant_password(email, current_password, new_password):
    """Change password for a participant"""
    try:
        # First verify current password
        if not check_participant_login(email, current_password):
            st.error("Current password is incorrect.")
            return False
            
        # Then update to new password
        password_hash = generate_password_hash(new_password)
        execute_query('UPDATE "Participants_list" SET "PasswordHash" = %s WHERE "Email" = %s', (password_hash, email))
        return True
    except Exception as e:
        st.error(f"Failed to change password: {str(e)}")
        return False

def show_login_page():
    """Show the login page with admin and participant login options"""
    st.title("GenAI Cohort Portal")
    
    st.subheader("Login")
    login_email = st.text_input("Email", key="login_email")
    login_password = st.text_input("Password", type="password", key="login_password")
    
    if st.button("Login", key="login_button"):
        if not login_email or not login_password:
            st.error("Please enter both email and password.")
            return
        
        # First try admin login
        if check_admin_login(login_email, login_password):
            st.session_state.logged_in = True
            st.session_state.user_role = "admin"
            st.session_state.user_email = login_email
            st.rerun()
            return
        
        # Then try participant login
        try:
            if check_participant_login(login_email, login_password):
                st.session_state.logged_in = True
                st.session_state.user_role = "participant"
                st.session_state.user_email = login_email
                st.rerun()
                return
        except Exception as e:
            st.error(f"Login error: {str(e)}")
        
        st.error("Invalid email or password.")
    
    # Add help text
    st.markdown("""
    ---
    ### Need Help?
    - If you're a participant and don't have login credentials, please contact the admin
    - For any login issues, please reach out to the admin at the provided contact email
    """)

def main():
    """Main application entry point"""
    # Add logout button in sidebar if logged in
    if st.session_state.logged_in:
        st.sidebar.info(f"Logged in as: {st.session_state.user_email}")
        if st.sidebar.button("Logout"):
            st.session_state.logged_in = False
            st.session_state.user_role = None
            st.session_state.user_email = None
            st.session_state.user_name = None
            st.rerun()
    
    # Validate configurations
    if not st.session_state.logged_in:
        missing_configs = validate_secrets()
        if missing_configs:
            st.error("Missing required configurations:")
            for msg in missing_configs:
                st.error(f"- {msg}")
            st.error("Please check your secrets.toml file.")
            return
    
    # Main app router
    if not st.session_state.logged_in:
        show_login_page()
    else:
        if st.session_state.user_role == "admin":
            show_admin_view()
        elif st.session_state.user_role == "participant":
            show_participant_view()

if __name__ == "__main__":
    main() 