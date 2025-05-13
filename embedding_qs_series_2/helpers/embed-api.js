// Server-side API with JWT

const jwt = require("jsonwebtoken");
const { v4: uuid } = require("uuid");
const dotenv = require("dotenv");

// Load environment variables from .env
dotenv.config();

/**
 * Generate a signed Sigma embed URL based on the provided QuickStart mode.
 *
 * @param {string} [mode] - Optional QuickStart-specific mode (e.g., 'getting_started')
 * @returns {Promise<string>} - Signed URL ready to embed
 */

async function generateSignedUrl(mode = "") {
  try {
    // Get current time for token generation
    const now = Math.floor(Date.now() / 1000);

    // Calculate token expiration time (default 1 hour, max 30 days)
    const expirationTime =
      now + Math.min(parseInt(process.env.SESSION_LENGTH) || 3600, 2592000);

    // Build mode-specific prefix (e.g., "GETTING_STARTED_")
    const modePrefix = mode ? `${mode.toUpperCase()}_` : "";

    // Lookup the correct BASE_URL from the .env
    const baseUrl = process.env[`${modePrefix}BASE_URL`];

    // Validate that a BASE_URL was found
    if (!baseUrl) {
      throw new Error(`Mode "${mode}" not properly configured in .env file.`);
    }

    // Lookup user-related fields; fall back to shared default if not overridden
    const email = process.env[`${modePrefix}EMAIL`] || process.env.EMAIL;
    const accountType =
      process.env[`${modePrefix}ACCOUNT_TYPE`] || process.env.ACCOUNT_TYPE;
    const rawTeams = process.env[`${modePrefix}TEAMS`] || process.env.TEAMS;

    // Convert comma-separated teams string into array
    const teamsArray = rawTeams ? rawTeams.split(",").map((t) => t.trim()) : [];

    // Gather user attributes from .env
    const userAttributes = {
      Store_Region: process.env.UA_STORE_REGION
    };

    // Create the payload for the JWT
    const payload = {
      sub: email, // Subject = user email
      iss: process.env.CLIENT_ID, // Issuer = Sigma Client ID
      jti: uuid(), // Unique token ID
      iat: now, // Issued at time
      exp: expirationTime, // Expiration time
      account_type: accountType, // Account type (e.g., "View", "Team")
      teams: teamsArray, // Teams (array even if only 1)
      user_attributes: userAttributes // Inject user attributes here
    };

    // Sign the JWT using shared secret
    const token = jwt.sign(payload, process.env.SECRET, {
      algorithm: "HS256",
      keyid: process.env.CLIENT_ID,
    });

    // Build the final embed URL using the mode-specific BASE_URL
    const signedEmbedUrl = `${baseUrl}?:jwt=${encodeURIComponent(
      token
    )}&:embed=true`;

    // Debug logs (useful during development)
    console.log("Mode:", mode || "default");
    console.log("BASE_URL:", baseUrl); // use the looked-up baseUrl
    console.log("CLIENT_ID:", process.env.CLIENT_ID);
    console.log("SESSION_LENGTH:", process.env.SESSION_LENGTH);
    console.log("TEAMS:", teamsArray);
    console.log("ACCOUNT_TYPE:", accountType);
    console.log("Signed Embed URL:", signedEmbedUrl);
    console.log("User Attributes:", userAttributes);

    // Optional URL parameters (comment/uncomment to test)
    const optionalParams = {
      disable_mobile_view: process.env.disable_mobile_view,
      hide_menu: process.env.hide_menu,
      hide_folder_navigation: process.env.hide_folder_navigation,
      hide_tooltip: process.env.hide_tooltip,
      lng: process.env.lng,
      menu_position: process.env.menu_position,
      responsive_height: process.env.responsive_height,
      theme: process.env.theme,
    };

    // Build query string for active optional params
    const optionalQuery = Object.entries(optionalParams)
      .filter(([key, value]) => value !== undefined && value !== "")
      .map(([key, value]) => `:${key}=${encodeURIComponent(value)}`)
      .join("&");

    // Append optional params if any are active
    const finalEmbedUrl = optionalQuery
      ? `${signedEmbedUrl}&${optionalQuery}`
      : signedEmbedUrl;

    // Debug logs for optional params
    console.log("Optional Parameters:", optionalParams);
    console.log("Final Embed URL:", finalEmbedUrl);

    return { signedUrl: finalEmbedUrl, jwt: token };
  } catch (error) {
    console.error("Failed to generate JWT:", error.message);
    throw new Error("JWT generation failed");
  }
}

// Export the function to server.js
module.exports = { generateSignedUrl };
