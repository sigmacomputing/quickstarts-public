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
    const now = Math.floor(Date.now() / 1000);
    const expirationTime =
      now + Math.min(parseInt(process.env.SESSION_LENGTH) || 3600, 2592000);

    const modePrefix = mode ? `${mode.toUpperCase()}_` : "";

    const baseUrl = process.env[`${modePrefix}BASE_URL`];
    if (!baseUrl) {
      throw new Error(`Mode "${mode}" not properly configured in .env file.`);
    }

    const email = process.env[`${modePrefix}EMAIL`] || process.env.EMAIL;
    const accountType =
      process.env[`${modePrefix}ACCOUNT_TYPE`] || process.env.ACCOUNT_TYPE;
    const rawTeams = process.env[`${modePrefix}TEAMS`] || process.env.TEAMS;
    const teamsArray = rawTeams ? rawTeams.split(",").map((t) => t.trim()) : [];

    // Collect user attributes based on ua_ prefix (case-sensitive)
    // We use "ua_" to differentiate user attributes from other environment variables
    const userAttributes = {};
    Object.entries(process.env).forEach(([key, value]) => {
      const prefix = `${modePrefix}ua_`;
      if (key.startsWith(prefix) && value) {
        const attrName = key.slice(prefix.length); // remove ua_ prefix
        userAttributes[attrName] = value.trim();
      }
    });

    // Validate and enforce fallback for DRS_REGION if used
    const rawRegionRole = userAttributes.DRS_REGION;
    if (rawRegionRole) {
      const validRoles = [
        "DRS_EXECUTIVE",
        "DRS_WEST",
        "DRS_EAST",
        "DRS_DEFAULT",
      ];
      const cleanedRole = rawRegionRole.trim().toUpperCase();
      if (!validRoles.includes(cleanedRole)) {
        console.warn(
          `Invalid DRS_REGION "${rawRegionRole}" passed. Falling back to DRS_DEFAULT.`
        );
        userAttributes.DRS_REGION = "DRS_DEFAULT";
      } else {
        userAttributes.DRS_REGION = cleanedRole; // Normalize to upper case
      }
    }

    // Construct the JWT payload
    const payload = {
      sub: email,
      iss: process.env.CLIENT_ID,
      jti: uuid(),
      iat: now,
      exp: expirationTime,
      account_type: accountType,
      teams: teamsArray,
      user_attributes: userAttributes,
    };

    const token = jwt.sign(payload, process.env.SECRET, {
      algorithm: "HS256",
      keyid: process.env.CLIENT_ID,
    });

    const signedEmbedUrl = `${baseUrl}?:jwt=${encodeURIComponent(
      token
    )}&:embed=true`;

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

    const optionalQuery = Object.entries(optionalParams)
      .filter(([_, value]) => value !== undefined && value !== "")
      .map(([key, value]) => `:${key}=${encodeURIComponent(value)}`)
      .join("&");

    const finalEmbedUrl = optionalQuery
      ? `${signedEmbedUrl}&${optionalQuery}`
      : signedEmbedUrl;

    // Logging
    console.log("Mode:", mode || "default");
    console.log("BASE_URL:", baseUrl);
    console.log("CLIENT_ID:", process.env.CLIENT_ID);
    console.log("SESSION_LENGTH:", process.env.SESSION_LENGTH);
    console.log("TEAMS:", teamsArray);
    console.log("ACCOUNT_TYPE:", accountType);
    console.log("User Attributes:", userAttributes);
    console.log("Optional Parameters:", optionalParams);
    console.log("Final Embed URL:", finalEmbedUrl);

    return { signedUrl: finalEmbedUrl, jwt: token };
  } catch (error) {
    console.error("Failed to generate JWT:", error.message);
    throw new Error("JWT generation failed");
  }
}

module.exports = { generateSignedUrl };
