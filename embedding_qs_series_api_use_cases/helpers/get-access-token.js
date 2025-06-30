require("dotenv").config();
const axios = require("axios");

const authURL = process.env.AUTH_URL;
const clientId = process.env.CLIENT_ID;
const secret = process.env.SECRET;

console.log("DEBUG ENV AUTH_URL:", authURL);
console.log("DEBUG ENV CLIENT_ID:", clientId ? "[set]" : "[missing]");
console.log("DEBUG ENV SECRET:", secret ? "[set]" : "[missing]");

let cachedToken = null;
let tokenExpiry = 0; // Epoch time in seconds

async function getBearerToken() {
  const now = Math.floor(Date.now() / 1000); // current time in seconds

  // Return cached token if still valid (add buffer of 60 seconds)
  if (cachedToken && now < tokenExpiry - 60) {
    console.log("Reusing cached bearer token");
    return cachedToken;
  }

  try {
    const requestData = new URLSearchParams({
      grant_type: "client_credentials",
      client_id: clientId,
      client_secret: secret,
    });

    console.log(`URL sent to Sigma: ${authURL}`);

    const response = await axios.post(authURL, requestData, {
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
    });

    cachedToken = response.data.access_token;
    const expiresIn = response.data.expires_in || 3600; // fallback to 1 hour
    tokenExpiry = now + expiresIn;

    console.log("Bearer token obtained successfully:", cachedToken);
    return cachedToken;
  } catch (error) {
    console.error("Error obtaining Bearer token:", error.response?.data || error.message);
    return null;
  }
}

if (require.main === module) {
  getBearerToken()
    .then((token) => console.log("Token acquired:", token))
    .catch((err) => console.error("Failed to acquire token:", err));
}

module.exports = getBearerToken;
