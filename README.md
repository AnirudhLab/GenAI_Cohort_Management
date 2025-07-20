# GenAI Cohort Management Portal

A Streamlit-based web application for managing GenAI cohort participants, teams, projects, and progress tracking.

## Features

### 1. User Management
- **Secure Login System**
  - Admin login with configurable credentials
  - Participant login using email and password
  - Password management for both admin and participants

### 2. Team Management
- Create and delete teams
- Assign participants to teams
- View team compositions and member details
- Automatic email notifications for team assignments

### 3. Project Management
- Create and assign projects to teams
- Track project progress through SDLC phases
- Delete projects when completed
- Email notifications for project assignments

### 4. Progress Tracking
- **SDLC Phase Tracking**
  - Requirements
  - Design
  - Implementation
  - Testing
  - Deployment
  - Maintenance
- Phase-wise progress updates
- Overall project progress monitoring
- Comments and status updates for each phase

### 5. Team Updates Dashboard
- Participants can post progress updates
- Like and comment on updates
- Filter updates by team
- Track update history

### 6. Email Notifications
- Team assignment notifications
- Project assignment notifications
- Password reset notifications
- Optional email notifications via Gmail SMTP

## Setup Instructions

### 1. Prerequisites
```bash
# Install Python 3.11 or later
python --version

# Install required packages
pip install -r requirements.txt
```

### 2. Google Sheets Setup
1. Create a Google Cloud Project
2. Enable Google Sheets API
3. Create service account credentials
4. Share your Google Sheet with the service account email
5. Download service account JSON key

### 3. Configuration
Create `.streamlit/secrets.toml` with the following structure:
```toml
[admin]
email = "admin@example.com"
password = "your_admin_password"

[gmail]
sender_email = "your_email@gmail.com"
app_password = "your_gmail_app_password"

[google]
google_sheet_url = "your_google_sheet_url"

[gspread]
type = "service_account"
project_id = "your_project_id"
private_key_id = "your_private_key_id"
private_key = "your_private_key"
client_email = "your_client_email"
client_id = "your_client_id"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "your_cert_url"
```

### 4. Running the Application
```bash
streamlit run app.py
```

## Google Sheets Structure

The application uses the following sheets:
1. **Participants_list**: Stores participant information and credentials
2. **Teams**: Stores team information
3. **Projects**: Stores project details and progress
4. **Updates**: Stores team updates
5. **Comments**: Stores comments on updates
6. **Likes**: Stores likes on updates
7. **ProjectProgress**: Stores detailed SDLC phase progress

## Features for Participants

1. **Dashboard**
   - View team information
   - See assigned projects
   - Track project progress
   - Submit progress updates

2. **Updates**
   - Post updates about their work
   - Like and comment on team updates
   - View updates from team members

3. **Account Management**
   - Change password
   - View profile information

## Features for Admins

1. **Team Management**
   - Create/delete teams
   - Assign participants to teams
   - View team compositions

2. **Project Management**
   - Create/delete projects
   - Assign projects to teams
   - Send notifications

3. **Progress Tracking**
   - Monitor all projects
   - Track SDLC phases
   - View team updates

4. **Password Management**
   - Reset participant passwords
   - Manage access control

## Security Features

1. **Password Security**
   - Secure password hashing
   - Minimum password length enforcement
   - Password reset functionality

2. **Access Control**
   - Role-based access (Admin/Participant)
   - Secure session management
   - Protected routes

3. **Data Protection**
   - Google Sheets API security
   - SMTP email security
   - Cached data management

## Troubleshooting

1. **Google Sheets API Quota**
   - The app implements caching to handle API limits
   - Cache duration: 5 minutes
   - Use refresh button to force update

2. **Email Notifications**
   - Requires valid Gmail app password
   - Check spam folder for notifications
   - Verify SMTP settings in secrets.toml

3. **Common Issues**
   - Clear cache if data seems outdated
   - Check Google Sheets permissions
   - Verify all required columns exist

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details. 