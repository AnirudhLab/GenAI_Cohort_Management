import pytest
from unittest.mock import MagicMock

# Since app.py is a streamlit app, we need to be careful with imports
# and what we test. We will focus on testing the business logic.

# We will mock streamlit and its components
st = MagicMock()

# We need to mock the db.py functions as well
db = MagicMock()

# Now we can import the functions from app.py
from app import check_admin_login, check_participant_login, reset_participant_password, change_participant_password, execute_query

def test_check_admin_login_success(mocker):
    mocker.patch('app.st.secrets', {
        "admin": {
            "email": "admin@test.com",
            "password": "password"
        }
    })
    assert check_admin_login("admin@test.com", "password") == True

def test_check_admin_login_wrong_password(mocker):
    mocker.patch('app.st.secrets', {
        "admin": {
            "email": "admin@test.com",
            "password": "password"
        }
    })
    assert check_admin_login("admin@test.com", "wrong_password") == False

def test_check_admin_login_wrong_email(mocker):
    mocker.patch('app.st.secrets', {
        "admin": {
            "email": "admin@test.com",
            "password": "password"
        }
    })
    assert check_admin_login("wrong@test.com", "password") == False

def test_check_participant_login_success(mocker):
    mocker.patch('app.execute_query', return_value=("hashed_password",))
    mocker.patch('app.check_password_hash', return_value=True)
    assert check_participant_login("participant@test.com", "password") == True

def test_check_participant_login_no_user(mocker):
    mocker.patch('app.execute_query', return_value=None)
    assert check_participant_login("nonexistent@test.com", "password") == False

def test_check_participant_login_wrong_password(mocker):
    mocker.patch('app.execute_query', return_value=("hashed_password",))
    mocker.patch('app.check_password_hash', return_value=False)
    assert check_participant_login("participant@test.com", "wrong_password") == False

def test_reset_participant_password(mocker):
    mock_execute_query = mocker.patch('app.execute_query')
    mocker.patch('app.generate_password_hash', return_value="new_hashed_password")

    reset_participant_password("participant@test.com", "new_password")

    mock_execute_query.assert_called_with(
        'UPDATE "Participants_list" SET "PasswordHash" = %s WHERE "Email" = %s',
        ("new_hashed_password", "participant@test.com")
    )

def test_change_participant_password_success(mocker):
    mocker.patch('app.check_participant_login', return_value=True)
    mock_execute_query = mocker.patch('app.execute_query')
    mocker.patch('app.generate_password_hash', return_value="new_hashed_password")

    assert change_participant_password("participant@test.com", "old_password", "new_password") == True
    mock_execute_query.assert_called_with(
        'UPDATE "Participants_list" SET "PasswordHash" = %s WHERE "Email" = %s',
        ("new_hashed_password", "participant@test.com")
    )

def test_change_participant_password_wrong_current_password(mocker):
    mocker.patch('app.check_participant_login', return_value=False)
    assert change_participant_password("participant@test.com", "wrong_old_password", "new_password") == False

from app import create_participant

def test_create_participant_success(mocker):
    # Simulate that the participant does not exist
    mock_execute_query = mocker.patch('app.execute_query')
    mock_execute_query.return_value = None

    result = create_participant("New Participant", "new@test.com", "Team A")

    assert result == True
    mock_execute_query.assert_any_call('SELECT "Email" FROM "Participants_list" WHERE "Email" = %s', ('new@test.com',), fetch="one")
    mock_execute_query.assert_any_call(
        'INSERT INTO "Participants_list" ("Name", "Email", "Team", "Status") VALUES (%s, %s, %s, %s)',
        ('New Participant', 'new@test.com', 'Team A', 'Pending')
    )

def test_create_participant_already_exists(mocker):
    # Simulate that the participant already exists
    mock_execute_query = mocker.patch('app.execute_query')
    mock_execute_query.return_value = ("new@test.com",)

    result = create_participant("New Participant", "new@test.com", "Team A")

    assert result == False
    mock_execute_query.assert_called_once_with('SELECT "Email" FROM "Participants_list" WHERE "Email" = %s', ('new@test.com',), fetch="one")
