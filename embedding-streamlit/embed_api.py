import hashlib
import hmac
import time
import uuid
from urllib.parse import quote

def urlencode(pairs):
    """Custom URL encoder that preserves colons and commas in the parameters."""
    def myquote(val):
        return quote(str(val), safe=",:")  # Ensure colons and commas are not percent-encoded
    # Encode each key-value pair and join them into a query string
    return "&".join(myquote(k) + "=" + myquote(v) for k, v in pairs.items())

def generate_signed_url(
    embed_path, client_id, embed_secret, sigma_team,
    user_email="user@example.com", user_id="1", session_length="3600", mode="userbacked"
):
    """
    Generates a signed URL for embedding Sigma into Streamlit.

    Parameters:
    - embed_path: The base URL for the Sigma embed.
    - client_id: Your Sigma client ID.
    - embed_secret: Your Sigma embed secret.
    - sigma_team: The user's team in Sigma.
    - user_email: The user's email address.
    - user_id: The user's external ID.
    - session_length: Session length in seconds.
    - mode: Embedding mode.

    Returns:
    - url_with_signature: The signed URL ready to be used in an iframe.
    """
    # Set up the parameters required for the secure Sigma embed
    params = {
        ":nonce": str(uuid.uuid4()),           # Unique identifier for the request
        ":email": user_email,                  # User's email address
        ":external_user_id": user_id,          # User's external ID
        ":client_id": client_id,               # Your Sigma client ID
        ":time": str(int(time.time())),        # Current timestamp in seconds
        ":session_length": session_length,     # Session length in seconds
        ":mode": mode,                         # Embedding mode
        ":external_user_team": sigma_team,     # User's team in Sigma
        ":account_type": "embedUser",          # Account type for the embed
        # Add any custom parameters below
        # "Custom-Param": "Value",
    }

    # Generate the URL with parameters
    url_with_params = embed_path + "?" + urlencode(params)

    # Create the signature using HMAC-SHA256 algorithm
    signature = hmac.new(
        embed_secret.encode('utf-8'),          # Embed secret as the key
        url_with_params.encode('utf-8'),       # URL with parameters as the message
        hashlib.sha256                         # Hashing algorithm
    ).hexdigest()

    # Append the signature to the URL
    url_with_signature = url_with_params + "&" + urlencode({":signature": signature})

    return url_with_signature
