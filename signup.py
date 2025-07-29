import streamlit as st
from db import execute_query

# Configure page layout
st.set_page_config(page_title="GenAI Cohort Signup", layout="wide")

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
    try:
        execute_query(
            """
            INSERT INTO "Participants_list" (
                "Name", "Email", "Preferred Name", "Experience Level", "Have GenAI Experience?",
                "Background", "Why do you want to join?", "What are your goals?", "Role Preference 1",
                "Role Preference 2", "Skills for Role", "Can participate daily?", "Best Time to Meet",
                "Has computer & internet?", "Comfortable with Tools", "Other Tools Known", "Anything else?",
                "Willing to mentor future cohorts?", "Status"
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT ("Email") DO NOTHING
            """,
            (
                name, email, pref_name, exp_level, genai_exp,
                ", ".join(background), why_join, goals,
                role_pref1, role_pref2, skills,
                available, best_time, has_pc, ", ".join(tools),
                other_tools, additional_info, mentor_future, "Pending"
            ),
        )
        st.success("✅ Submitted successfully! Please wait for admin approval.")
    except Exception as e:
        st.error(f"❌ An error occurred while submitting: {e}")
