// File: embedding_qs_series_2_api_use_cases/helpers/get-access-token.js

require("dotenv").config();
const axios = require("axios");

const authURL = process.env.AUTH_URL;
const clientId = process.env.CLIENT_ID;
const secret = process.env.SECRET;

let cachedToken = null;
let tokenExpiry = 0; // Epoch time in seconds

/**
 * Uses OAuth2 client credentials flow to fetch a token from Sigma.
 * Caches token until expiration with a 60s buffer.
 *
 * @returns {Promise<string|null>} The bearer token or null if request fails.
 */
async function getBearerToken() {
  const now = Math.floor(Date.now() / 1000);

  if (cachedToken && now < tokenExpiry - 60) {
    if (process.env.DEBUG === "true") {
      console.log("Reusing cached bearer token");
    }
    return cachedToken;
  }

  try {
    const requestData = new URLSearchParams({
      grant_type: "client_credentials",
      client_id: clientId,
      client_secret: secret,
    });

    const response = await axios.post(authURL, requestData, {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });

    cachedToken = response.data.access_token;
    const expiresIn = response.data.expires_in || 3600;
    tokenExpiry = now + expiresIn;

    if (process.env.DEBUG === "true") {
      console.log("Bearer token obtained successfully");
    }

    return cachedToken;
  } catch (error) {
    const errorMsg =
      error.response?.data?.error_description ||
      error.response?.data?.error ||
      error.message;

    if (process.env.DEBUG === "true") {
      console.error("Error obtaining Bearer token:", errorMsg);
    }

    return null;
  }
}

// Optional: run standalone for testing
if (require.main === module) {
  getBearerToken()
    .then((token) => {
      if (process.env.DEBUG === "true") {
        console.log("Token acquired:", token);
      }
    })
    .catch((err) => {
      console.error("Failed to acquire token:", err.message);
    });
}

module.exports = getBearerToken;
