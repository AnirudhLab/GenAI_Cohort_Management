import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Configure page layout
st.set_page_config(page_title="GenAI Cohort Signup", layout="wide")

# Authenticate with Google Sheets using Streamlit Secrets
def get_google_sheet():
    try:
        # Define scope
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]

        # Fix private_key formatting from secrets
        creds_dict = dict(st.secrets["gspread"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

        # Authenticate and authorize
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)

        # Load Sheet using [google] section
        sheet_url = st.secrets["google"]["google_sheet_url"]
        sheet = client.open_by_url(sheet_url).sheet1
        return sheet

    except Exception as e:
        st.error("🔐 Google Sheet authentication failed.")
        st.exception(e)
        raise e

# Title
st.title("📝 AIEagles Sign Up for the GenAI Cohort")

# Form fields
name = st.text_input("Full Name")
email = st.text_input("Email")
pref_name = st.text_input("Preferred Name")
exp_level = st.selectbox("Experience Level", ["No experience", "Beginner", "Intermediate", "Advanced"])
genai_exp = st.checkbox("Have GenAI Experience?")
background = st.multiselect("Background", ["Student", "Professional", "Hobbyist", "Educator", "Other"])
why_join = st.text_area("Why do you want to join?")
goals = st.text_area("What are your goals?")
role_pref1 = st.selectbox("Role Preference 1", ["Project Lead", "AI Explorer", "Builder", "UX Designer", "Tester", "Documenter"])
role_pref2 = st.selectbox("Role Preference 2", ["Project Lead", "AI Explorer", "Builder", "UX Designer", "Tester", "Documenter"])
skills = st.text_area("Skills for Role")
available = st.checkbox("Can participate daily?")
best_time = st.selectbox("Best Time to Meet", ["Morning", "Midday", "Evening", "Flexible"])
has_pc = st.checkbox("Has computer & internet?")
tools = st.multiselect("Comfortable with Tools", ["Google Docs", "GitHub", "Notion"])
other_tools = st.text_input("Other Tools Known")
additional_info = st.text_area("Anything else?")
mentor_future = st.checkbox("Willing to mentor future cohorts?")

# Submit button
if st.button("Submit"):
    new_data = [
        name,
        email,
        pref_name,
        exp_level,
        genai_exp,
        ", ".join(background),
        why_join,
        goals,
        role_pref1,
        role_pref2,
        skills,
        available,
        best_time,
        has_pc,
        ", ".join(tools),
        other_tools,
        additional_info,
        mentor_future,
        "Pending"
    ]

    try:
        sheet = get_google_sheet()
        sheet.append_row(new_data)
        st.success("✅ Submitted successfully! Please wait for admin approval.")
    except Exception as e:
        st.error(f"❌ An error occurred while submitting: {e}")
