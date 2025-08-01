// File: helpers/get-embed-user-token.js
// Gets a bearer token for API calls acting as the specific embed user

require("dotenv").config();
const axios = require("axios");
const generateJwt = require("./create-jwt");

const DEBUG = process.env.DEBUG === "true";

let cachedToken = null;
let tokenExpiry = 0;

/**
 * Gets a bearer token that acts as the specific embed user (build.embed.qs@example.com)
 * This is different from the admin client credentials token - it has the permissions
 * and data access scope of the specific embed user.
 * 
 * @param {string} userEmail - Email of the embed user (defaults to BUILD_EMAIL)
 * @returns {Promise<string|null>} Bearer token for the embed user or null if failed
 */
async function getEmbedUserToken(userEmail = process.env.BUILD_EMAIL) {
  const now = Math.floor(Date.now() / 1000);

  // Check if we have a cached token that's still valid
  if (cachedToken && now < tokenExpiry - 60) {
    if (DEBUG) console.log("Reusing cached embed user token");
    return cachedToken;
  }

  try {
    // Generate a JWT for the embed user for API access
    // We use a dummy embed URL since we just need the user context
    const dummyEmbedUrl = `${process.env.EMBED_URL_BASE}/${process.env.ORG_SLUG}/workbook/dummy`;
    
    const embedJwt = generateJwt({
      embedUrl: dummyEmbedUrl,
      mode: "build",
      sub: userEmail,
      permissions: ["build", "view"]
    });

    // Exchange the embed JWT for an API bearer token
    const response = await axios.post(`${process.env.BASE_URL}/auth/token`, {
      grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer",
      assertion: embedJwt
    }, {
      headers: {
        "Content-Type": "application/json"
      }
    });

    cachedToken = response.data.access_token;
    const expiresIn = response.data.expires_in || 300; // Default 5 minutes for embed tokens
    tokenExpiry = now + expiresIn;

    if (DEBUG) console.log(`Embed user token obtained for: ${userEmail}`);
    return cachedToken;

  } catch (error) {
    if (DEBUG) {
      console.error("Error obtaining embed user token:", error.response?.data || error.message);
    }

    // Fallback to admin token if embed user token fails
    if (DEBUG) console.log("Falling back to admin client credentials token");
    
    try {
      const requestData = new URLSearchParams({
        grant_type: "client_credentials",
        client_id: process.env.CLIENT_ID,
        client_secret: process.env.SECRET,
      });

      const fallbackResponse = await axios.post(process.env.AUTH_URL, requestData, {
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
      });

      cachedToken = fallbackResponse.data.access_token;
      const expiresIn = fallbackResponse.data.expires_in || 3600;
      tokenExpiry = now + expiresIn;

      if (DEBUG) console.log("Fallback to admin token successful");
      return cachedToken;

    } catch (fallbackError) {
      if (DEBUG) console.error("Fallback token also failed:", fallbackError.message);
      return null;
    }
  }
}

module.exports = getEmbedUserToken;