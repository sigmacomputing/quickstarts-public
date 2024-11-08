import streamlit as st
import os
from dotenv import load_dotenv
from embed_api import generate_signed_url  # Import the function from embed-api.py

# Set the page configuration to use the full width of the browser window
st.set_page_config(layout="wide")

# Load environment variables from the .env file
load_dotenv()

# Retrieve variables from .env file
EMBED_PATH = os.getenv('EMBED_PATH')
CLIENT_ID = os.getenv('CLIENT_ID')
EMBED_SECRET = os.getenv('SECRET')
EMAIL = os.getenv('EMAIL')
EXTERNAL_USER_ID = os.getenv('EXTERNAL_USER_ID')
ACCOUNT_TYPE = os.getenv('ACCOUNT_TYPE')
EXTERNAL_USER_TEAM = os.getenv('EXTERNAL_USER_TEAM')
SESSION_LENGTH = os.getenv('SESSION_LENGTH', '3600')  # Set default to 3600 if not defined
MODE = os.getenv('MODE', 'userbacked')  # Set default to 'userbacked' if not defined

# Log key configuration details for debugging
st.write("### Sigma Embed Configuration")
st.write("EMBED_PATH:", EMBED_PATH)
st.write("CLIENT_ID:", CLIENT_ID)
st.write("EMAIL:", EMAIL)
st.write("EXTERNAL_USER_ID:", EXTERNAL_USER_ID)
st.write("ACCOUNT_TYPE:", ACCOUNT_TYPE)
st.write("EXTERNAL_USER_TEAM:", EXTERNAL_USER_TEAM)
st.write("SESSION_LENGTH:", SESSION_LENGTH)
st.write("MODE:", MODE)

# Apply external CSS styles if you have a "styles.css" file
def local_css(file_name):
    """Loads a local CSS file into the Streamlit app."""
    with open(file_name) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

local_css("styles.css")

# Display the Sigma embed in the Streamlit app
st.markdown(
    """
    <h1 style='text-align: center; margin-top: 10px; margin-bottom: 0px;'>
    Securely Embed Sigma into Streamlit 🎈
    </h1>
    """,
    unsafe_allow_html=True
)

# Generate the signed URL for the Sigma embed
url_with_signature = generate_signed_url(
    embed_path=EMBED_PATH,
    client_id=CLIENT_ID,
    embed_secret=EMBED_SECRET,
    sigma_team=EXTERNAL_USER_TEAM,
    user_email=EMAIL,
    user_id=EXTERNAL_USER_ID,
    session_length=SESSION_LENGTH,
    mode=MODE
)

# Use the full page width for the iframe and specify a height
st.components.v1.iframe(url_with_signature, height=800)
