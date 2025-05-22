import jwt
import time
import uuid

def generate_signed_url(base_url, client_id, secret, email, account_type, teams, session_length=3600):
    now = int(time.time())
    exp = now + min(int(session_length), 2592000)

    payload = {
        "sub": email,
        "iss": client_id,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": exp,
        "account_type": account_type,
        "teams": teams.split(",") if teams else [],
        "user_attributes": {}
    }

    token = jwt.encode(payload, secret, algorithm="HS256", headers={"kid": client_id})
    return f"{base_url}?:embed=true&:jwt={token}"
