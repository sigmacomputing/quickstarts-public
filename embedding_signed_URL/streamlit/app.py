import streamlit as st
import os
from dotenv import load_dotenv
from embed_api import generate_signed_url  # Import the function from embedding.py

# Set the page configuration to use the full width of the browser window
st.set_page_config(layout="wide")

# Load environment variables from the .env file
load_dotenv()

# Retrieve variables from environment
EMBED_PATH = os.getenv('EMBED_PATH')
CLIENT_ID = os.getenv('CLIENT_ID')
EMBED_SECRET = os.getenv('EMBED_SECRET')
SIGMA_TEAM = os.getenv('SIGMA_TEAM')

# Apply external CSS styles
def local_css(file_name):
    """Loads a local CSS file into the Streamlit app."""
    with open(file_name) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

local_css("styles.css")

# Generate the signed URL for the Sigma embed
url_with_signature = generate_signed_url(
    embed_path=EMBED_PATH,
    client_id=CLIENT_ID,
    embed_secret=EMBED_SECRET,
    sigma_team=SIGMA_TEAM,
    user_email="user@example.com",  # Replace with dynamic user email if available
    user_id="1"                     # Replace with dynamic user ID if available
)

# Display the Sigma embed in the Streamlit app
st.markdown(
    """
    <h1 style='text-align: center; margin-top: 10px; margin-bottom: 0px;'>
    Securely Embed Sigma into Streamlit 🎈
    </h1>
    """,
    unsafe_allow_html=True
)

# Use the full page width for the iframe
st.components.v1.iframe(url_with_signature)
