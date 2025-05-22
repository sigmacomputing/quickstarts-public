import streamlit as st
import os
from dotenv import load_dotenv
from embed_api import generate_signed_url  # This should return just the signed URL

# Load .env variables
load_dotenv()

# Set page layout
st.set_page_config(layout="wide")

# Required JWT params from .env
BASE_URL = os.getenv('BASE_URL')
CLIENT_ID = os.getenv('CLIENT_ID')
SECRET = os.getenv('SECRET')
EMAIL = os.getenv('EMAIL')
ACCOUNT_TYPE = os.getenv('ACCOUNT_TYPE')
TEAMS = os.getenv('TEAMS')
SESSION_LENGTH = int(os.getenv('SESSION_LENGTH', '3600'))

# Load local CSS (optional)
def local_css(file_name):
    with open(file_name) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

# Load local CSS
local_css("styles.css")

# Begin container
st.markdown("<div class='env-container'>", unsafe_allow_html=True)

st.write("### Sigma Embed Configuration")
st.write("BASE_URL:", BASE_URL)
st.write("CLIENT_ID:", CLIENT_ID)
st.write("EMAIL:", EMAIL)
st.write("ACCOUNT_TYPE:", ACCOUNT_TYPE)
st.write("TEAMS:", TEAMS)
st.write("SESSION_LENGTH:", SESSION_LENGTH)

# End container
st.markdown("</div>", unsafe_allow_html=True)


# Page heading
st.markdown(
    """
    <h1 style='text-align: center; margin-top: 10px; margin-bottom: 0px;'>
    Securely Embed Sigma into Streamlit 🎈
    </h1>
    """,
    unsafe_allow_html=True
)

# Generate the signed Sigma embed URL
signed_url = generate_signed_url(
    base_url=BASE_URL,
    client_id=CLIENT_ID,
    secret=SECRET,
    email=EMAIL,
    account_type=ACCOUNT_TYPE,
    teams=TEAMS,
    session_length=SESSION_LENGTH
)

# Display the iframe in Streamlit
st.components.v1.iframe(signed_url, height=800)
