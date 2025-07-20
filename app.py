import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from werkzeug.security import check_password_hash, generate_password_hash
import yagmail
import os
from datetime import datetime, timedelta
import requests
import json

# Initialize session state
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_role = None
    st.session_state.user_email = None
    st.session_state.gspread_client = None
    st.session_state.sheet_data_cache = {}
    st.session_state.last_sheet_refresh = {}

def validate_secrets():
    """Validate all required secrets are present"""
    required_configs = {
        "admin": ["email", "password"],
        "gmail": ["sender_email", "app_password"],
        "gspread": [
            "type", "project_id", "private_key_id", "private_key",
            "client_email", "client_id", "auth_uri", "token_uri"
        ],
        "google": ["google_sheet_url"]
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

def get_gspread_client():
    """Gets or creates a cached gspread client"""
    if st.session_state.gspread_client is not None:
        return st.session_state.gspread_client
        
    try:
        # Get the gspread credentials
        creds_dict = dict(st.secrets["gspread"])
        # Fix newlines in private key
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        st.session_state.gspread_client = client
        return client
    except Exception as e:
        st.error(f"Failed to initialize Google Sheets client: {str(e)}")
        return None

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

# Cache duration in minutes
CACHE_DURATION = 5

def get_cached_sheet_data(sheet_name, worksheet):
    """Gets sheet data from cache if valid, otherwise fetches from Google Sheets."""
    current_time = datetime.now()
    
    # Check if we have cached data and it's still valid
    if (sheet_name in st.session_state.sheet_data_cache and 
        sheet_name in st.session_state.last_sheet_refresh and 
        current_time - st.session_state.last_sheet_refresh[sheet_name] < timedelta(minutes=CACHE_DURATION)):
        return st.session_state.sheet_data_cache[sheet_name]
    
    # If no valid cache, fetch data from Google Sheets
    try:
        data = worksheet.get_all_records()
        # Update cache
        st.session_state.sheet_data_cache[sheet_name] = data
        st.session_state.last_sheet_refresh[sheet_name] = current_time
        return data
    except gspread.exceptions.APIError as e:
        if "429" in str(e):  # Quota exceeded error
            if sheet_name in st.session_state.sheet_data_cache:
                st.warning(f"API quota exceeded. Using cached data from {st.session_state.last_sheet_refresh[sheet_name].strftime('%H:%M:%S')}")
                return st.session_state.sheet_data_cache[sheet_name]
            else:
                st.error("API quota exceeded and no cached data available. Please wait a few minutes and try again.")
                raise e
        raise e
    except Exception as e:
        if sheet_name in st.session_state.sheet_data_cache:
            st.warning(f"Failed to fetch fresh data, using cached data from {st.session_state.last_sheet_refresh[sheet_name].strftime('%H:%M:%S')}")
            return st.session_state.sheet_data_cache[sheet_name]
        raise e

def clear_cache():
    """Clears the sheet data cache."""
    st.session_state.sheet_data_cache = {}
    st.session_state.last_sheet_refresh = {}

def get_sheet(sheet_name):
    """Gets a specific worksheet, creating it with headers if it doesn't exist."""
    client = get_gspread_client()
    
    # Use cached spreadsheet if available
    if 'spreadsheet' not in st.session_state:
        st.session_state.spreadsheet = client.open_by_url(st.secrets["google"]["google_sheet_url"])
    spreadsheet = st.session_state.spreadsheet
    
    # Define headers for each sheet type
    headers = {
        "Teams": ["TeamName", "Description"],  # Store team information
        "Participants_list": ["Name", "Email", "Preferred Name", "Experience Level", "Have GenAI Experience?", 
                            "Background", "Why do you want to join?", "What are your goals?", "Role Preference 1",
                            "Role Preference 2", "Skills for Role", "Can participate daily?", "Best Time to Meet",
                            "Has computer & internet?", "Comfortable with Tools", "Other Tools Known", "Anything else?",
                            "Willing to mentor future cohorts?", "Status", "Team"],
        "Projects": ["ProjectName", "AssignedTeam", "ProjectInfo", "CreatedAt", "CurrentPhase", "Progress"],
        "Updates": ["UpdateID", "Timestamp", "Team", "Email", "Update", "Phase"],
        "Comments": ["UpdateID", "Timestamp", "Email", "Comment"],
        "Likes": ["UpdateID", "Email"],
        "ProjectProgress": ["ProjectName", "Phase", "Status", "StartDate", "EndDate", "Comments"]
    }
    
    # Define SDLC phases
    if 'sdlc_phases' not in st.session_state:
        st.session_state.sdlc_phases = [
            "Requirements",
            "Design",
            "Implementation",
            "Testing",
            "Deployment",
            "Maintenance"
        ]
    
    try:
        # Use cached worksheet if available
        if f'worksheet_{sheet_name}' not in st.session_state:
            st.session_state[f'worksheet_{sheet_name}'] = spreadsheet.worksheet(sheet_name)
        worksheet = st.session_state[f'worksheet_{sheet_name}']
        
        # For Participants_list, don't modify the existing structure
        if sheet_name == "Participants_list":
            return worksheet
            
        # For other sheets, check if headers match expected headers
        current_headers = worksheet.row_values(1)
        expected_headers = headers.get(sheet_name, [])
        
        # If headers don't match or are missing, update them
        if current_headers != expected_headers:
            # Clear the worksheet
            worksheet.clear()
            # Update headers
            worksheet.append_row(expected_headers)
            
    except gspread.exceptions.WorksheetNotFound:
        # Create new worksheet with correct headers
        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1, cols=len(headers.get(sheet_name, [])))
        worksheet.append_row(headers.get(sheet_name, []))
        st.session_state[f'worksheet_{sheet_name}'] = worksheet
    
    return worksheet

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
        participants_sheet = get_sheet("Participants_list")
        if participants_sheet:
            # Ensure PasswordHash column exists
            add_password_column()
            
            participants_data = get_cached_sheet_data("Participants_list", participants_sheet)
            if participants_data:
                participants_df = pd.DataFrame(participants_data)
                
                # Clean the data - replace empty strings and NaN values
                participants_df = participants_df.fillna("")
                
                # Filter out rows where Email is empty
                participants_df = participants_df[
                    (participants_df["Email"].astype(str).str.strip() != "")
                ]
                
                # Use Preferred Name if available, otherwise use Name
                participants_df["Display Name"] = participants_df["Preferred Name"].where(
                    participants_df["Preferred Name"].astype(str).str.strip() != "",
                    participants_df["Name"]
                )
                
                # Add Team column if it doesn't exist
                if "Team" not in participants_df.columns:
                    participants_df["Team"] = ""
                
                # Fill empty team values with empty string
                participants_df["Team"] = participants_df["Team"].fillna("").astype(str)
                participants_df["Team"] = participants_df["Team"].replace({"nan": "", "None": "", "null": ""}).str.strip()
                
                # Ensure PasswordHash column exists in DataFrame
                if "PasswordHash" not in participants_df.columns:
                    participants_df["PasswordHash"] = ""
            else:
                st.warning("No participant data found. Please check the Participants_list sheet.")
        
        # Load teams
        teams_sheet = get_sheet("Teams")
        if teams_sheet:
            teams_data = get_cached_sheet_data("Teams", teams_sheet)
            teams_df = pd.DataFrame(teams_data) if teams_data else pd.DataFrame()
            available_teams = [] if teams_df.empty else teams_df["TeamName"].tolist()
    
    except Exception as e:
        st.error(f"Error loading data: {str(e)}")
        st.error("Please check your Google Sheets connection and permissions.")
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
                                new_team = [new_team_name, team_description]
                                teams_sheet.append_row(new_team)
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
                            if participants_df is not None:
                                participants_df.loc[participants_df["Team"] == team_to_delete, "Team"] = ""
                                participants_sheet.update([participants_df.columns.values.tolist()] + participants_df.values.tolist())
                            
                            # Delete team from Teams sheet
                            team_row = teams_df[teams_df["TeamName"] == team_to_delete].index[0] + 2  # +2 for header and 0-based index
                            teams_sheet.delete_rows(team_row)
                            
                            st.success(f"Team '{team_to_delete}' deleted successfully!")
                            clear_cache()
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to delete team: {str(e)}")
        
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
                            
                            # Update DataFrame with team assignments
                            for participant in selected_participants:
                                # Get participant's email
                                participant_row = participants_df[participants_df["Display Name"] == participant].iloc[0]
                                participant_email = participant_row["Email"]
                                
                                # Update team assignment
                                participants_df.loc[
                                    participants_df["Display Name"] == participant, 
                                    "Team"
                                ] = selected_team
                                
                                # Try to send notification
                                if notify_participant(participant_email, participant, selected_team):
                                    notifications_sent.append(participant)
                                else:
                                    failed_notifications.append(participant)

                            # Update Google Sheet with new team assignments
                            participants_sheet.update([participants_df.columns.values.tolist()] + participants_df.values.tolist())
                            
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
                    # Add project to Projects sheet
                    projects_sheet = get_sheet("Projects")
                    timestamp = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
                    new_project = [
                        project_name,
                        project_description,
                        assigned_team,
                        timestamp,  # CreatedAt
                        "Requirements",  # CurrentPhase - start with first SDLC phase
                        "0"  # Progress - start at 0%
                    ]
                    projects_sheet.append_row(new_project)
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
        projects_sheet = get_sheet("Projects")
        projects_data = get_cached_sheet_data("Projects", projects_sheet)
        
        if not projects_data:
            st.info("No projects created yet.")
            return
            
        projects_df = pd.DataFrame(projects_data)
        
        # Ensure all required columns exist
        if len(projects_df.columns) < 6:
            st.error("Project data format is incorrect. Please contact admin.")
            return
            
        projects_df.columns = ["Project Name", "Description", "Assigned Team", "Created At", "Current Phase", "Progress"]
        
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
                                        # Delete project from sheet (add 2 for header and 0-based index)
                                        projects_sheet.delete_rows(idx + 2)
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
        updates_sheet = get_sheet("Updates")
        comments_sheet = get_sheet("Comments")
        likes_sheet = get_sheet("Likes")
        
        updates_data = get_cached_sheet_data("Updates", updates_sheet)
        comments_data = get_cached_sheet_data("Comments", comments_sheet)
        likes_data = get_cached_sheet_data("Likes", likes_sheet)
        
        if not updates_data:
            st.info("No updates posted yet.")
            return
            
        # Convert to DataFrames
        updates_df = pd.DataFrame(updates_data)
        comments_df = pd.DataFrame(comments_data) if comments_data else pd.DataFrame(columns=["UpdateID", "Timestamp", "Email", "Comment"])
        likes_df = pd.DataFrame(likes_data) if likes_data else pd.DataFrame(columns=["UpdateID", "Email"])
        
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
                            like_idx = likes_df[
                                (likes_df["UpdateID"] == update["UpdateID"]) &
                                (likes_df["Email"] == user_email)
                            ].index[0]
                            like_row = like_idx + 2  # Add 2 for header and 0-based index
                            likes_sheet.delete_rows(like_row)
                        else:
                            # Add like using named parameters
                            likes_sheet.append_row([update["UpdateID"], user_email])
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
                            # Add comment using named parameters
                            comments_sheet.append_row([
                                update["UpdateID"],
                                pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                                user_email,
                                new_comment
                            ])
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
        projects_sheet = get_sheet("Projects")
        progress_sheet = get_sheet("ProjectProgress")
        
        projects_data = get_cached_sheet_data("Projects", projects_sheet)
        progress_data = get_cached_sheet_data("ProjectProgress", progress_sheet)
        
        if not projects_data:
            st.info("No projects created yet.")
            return
            
        # Convert to DataFrames
        projects_df = pd.DataFrame(projects_data)
        progress_df = pd.DataFrame(progress_data) if progress_data else pd.DataFrame(columns=["ProjectName", "Phase", "Status", "StartDate", "EndDate", "Comments"])
        
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
                            # Update project's current phase and progress
                            project_idx = projects_df[projects_df["ProjectName"] == selected_project].index[0]
                            project_row = project_idx + 2  # Add 2 for header and 0-based index
                            
                            # Update using named parameters to avoid range errors
                            projects_sheet.update(
                                range_name=f'E{project_row}',
                                values=[[phase]],  # CurrentPhase
                            )
                            projects_sheet.update(
                                range_name=f'F{project_row}',
                                values=[[str(progress)]],  # Progress
                            )
                            
                            # Update or add phase progress
                            new_progress = [
                                selected_project,
                                phase,
                                status,
                                start_date.strftime("%Y-%m-%d"),
                                end_date.strftime("%Y-%m-%d") if end_date else "",
                                comments
                            ]
                            
                            # Check if phase entry exists
                            existing_progress = project_progress[project_progress["Phase"] == phase]
                            if not existing_progress.empty:
                                # Update existing entry
                                row_idx = existing_progress.index[0] + 2
                                progress_sheet.update(
                                    range_name=f'A{row_idx}:F{row_idx}',
                                    values=[new_progress],
                                )
                            else:
                                # Add new entry
                                progress_sheet.append_row(new_progress)
                            
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
        participants_sheet = get_sheet("Participants_list")
        participants_data = get_cached_sheet_data("Participants_list", participants_sheet)
        participants_df = pd.DataFrame(participants_data)
        
        projects_sheet = get_sheet("Projects")
        projects_data = get_cached_sheet_data("Projects", projects_sheet)
        projects_df = pd.DataFrame(projects_data)
        
        # Find user's team and project
        user_info = participants_df[participants_df["Email"] == user_email].iloc[0]
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
                    updates_sheet = get_sheet("Updates")
                    # Generate a unique ID for the update
                    update_id = f"upd_{pd.Timestamp.now().strftime('%Y%m%d%H%M%S')}_{user_email}"
                    timestamp = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    # Add update using named parameters
                    updates_sheet.append_row([
                        update_id,
                        timestamp,
                        user_team,
                        user_email,
                        update_text,
                        phase if phase else ""
                    ])
                    st.success("Your update has been submitted successfully!")
                    clear_cache()
                except Exception as e:
                    st.error(f"Failed to submit update: {str(e)}")
    
    with updates_tab:
        show_updates_dashboard(user_email, "participant")

# --- 4. MAIN APP & LOGIN LOGIC ---

def add_password_column():
    """Add PasswordHash column to Participants_list sheet if it doesn't exist"""
    try:
        participants_sheet = get_sheet("Participants_list")
        headers = participants_sheet.row_values(1)
        
        if "PasswordHash" not in headers:
            # Add PasswordHash column
            headers.append("PasswordHash")
            # Get current number of columns
            num_cols = len(headers)
            # Add new column
            participants_sheet.add_cols(1)
            # Update headers
            participants_sheet.update('A1', [headers])
            # Initialize all password hashes as empty
            data = participants_sheet.get_all_records()
            for i, row in enumerate(data):
                # Update just the new column
                participants_sheet.update_cell(i+2, num_cols, "")
            return True
        return True
    except Exception as e:
        st.error(f"Failed to add password column: {str(e)}")
        return False

def reset_participant_password(email, new_password):
    """Reset password for a participant"""
    try:
        participants_sheet = get_sheet("Participants_list")
        data = participants_sheet.get_all_records()
        headers = participants_sheet.row_values(1)
        
        # Ensure PasswordHash column exists
        if "PasswordHash" not in headers:
            if not add_password_column():
                return False
            headers = participants_sheet.row_values(1)
        
        # Find participant row
        for i, row in enumerate(data):
            if row.get("Email") == email:
                # Generate new password hash
                password_hash = generate_password_hash(new_password)
                
                # Update row with new password hash
                row_data = [row.get(header, "") for header in headers]
                password_col = headers.index("PasswordHash")
                row_data[password_col] = password_hash
                
                # Update sheet (add 2 to account for 1-based indexing and header row)
                participants_sheet.update(f'A{i+2}', [row_data])
                return True
                
        return False
    except Exception as e:
        st.error(f"Failed to reset password: {str(e)}")
        return False

def check_participant_login(email, password):
    """Check participant credentials from Google Sheet"""
    try:
        participants_sheet = get_sheet("Participants_list")
        participants_data = get_cached_sheet_data("Participants_list", participants_sheet)
        
        if not participants_data:
            st.error("No participant data found.")
            return False
            
        participants_df = pd.DataFrame(participants_data)
        
        if "Email" not in participants_df.columns:
            st.error("Invalid participant data format. Please contact admin.")
            return False
        
        user_record = participants_df[participants_df["Email"] == email]
        
        if user_record.empty:
            st.error("Email not found. Please check your email or contact admin.")
            return False
        
        # Check if user has a password hash
        if "PasswordHash" not in participants_df.columns:
            st.error("Password authentication not set up. Please contact admin.")
            return False
        
        user_password_hash = user_record.iloc[0].get("PasswordHash")
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
        participants_sheet = get_sheet("Participants_list")
        data = participants_sheet.get_all_records()
        headers = participants_sheet.row_values(1)
        
        # Ensure PasswordHash column exists
        if "PasswordHash" not in headers:
            if not add_password_column():
                return False
            headers = participants_sheet.row_values(1)
        
        # Find participant row
        for i, row in enumerate(data):
            if row.get("Email") == email:
                # Generate new password hash
                password_hash = generate_password_hash(new_password)
                
                # Update row with new password hash
                row_data = [row.get(header, "") for header in headers]
                password_col = headers.index("PasswordHash")
                row_data[password_col] = password_hash
                
                # Update sheet (add 2 to account for 1-based indexing and header row)
                participants_sheet.update(f'A{i+2}', [row_data])
                return True
                
        return False
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