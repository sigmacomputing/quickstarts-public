const jwt = require("jsonwebtoken");
const { v4: uuid } = require("uuid");
const dotenv = require("dotenv");

dotenv.config();

/**
 * Generate a signed Sigma embed URL based on the provided QuickStart mode.
 *
 * @param {string} [mode] - Optional QuickStart-specific mode (e.g., 'link_sharing')
 * @param {Object} [query={}] - Express req.query object containing optional exploreKey/bookmarkId
 * @returns {Promise<{ signedUrl: string, jwt: string }>}
 */
async function generateSignedUrl(mode = "", query = {}) {
  try {
    const now = Math.floor(Date.now() / 1000);
    const expirationTime =
      now + Math.min(parseInt(process.env.SESSION_LENGTH) || 3600, 2592000);

    const modePrefix = mode ? `${mode.toUpperCase()}_` : "";

    // Load core config from .env with support for QuickStart-specific overrides
    const baseUrl = process.env[`${modePrefix}BASE_URL`];
    if (!baseUrl) {
      throw new Error(`Mode "${mode}" not properly configured in .env file.`);
    }

    const email = process.env[`${modePrefix}EMAIL`] || process.env.EMAIL;
    const accountType =
      process.env[`${modePrefix}ACCOUNT_TYPE`] || process.env.ACCOUNT_TYPE;
    const rawTeams = process.env[`${modePrefix}TEAMS`] || process.env.TEAMS;
    const teamsArray = rawTeams ? rawTeams.split(",").map((t) => t.trim()) : [];

    // Pull user attributes from .env using "ua_" prefix
    const userAttributes = {};
    Object.entries(process.env).forEach(([key, value]) => {
      const prefix = `${modePrefix}ua_`;
      if (key.startsWith(prefix) && value) {
        const attrName = key.slice(prefix.length);
        userAttributes[attrName] = value.trim();
      }
    });

    // Normalize DRS_REGION if defined
    const rawRegionRole = userAttributes.DRS_REGION;
    if (rawRegionRole) {
      const validRoles = [
        "DRS_EXECUTIVE",
        "DRS_WEST",
        "DRS_EAST",
        "DRS_DEFAULT",
      ];
      const cleanedRole = rawRegionRole.trim().toUpperCase();
      userAttributes.DRS_REGION = validRoles.includes(cleanedRole)
        ? cleanedRole
        : "DRS_DEFAULT";
    }

    // Define the core payload for the JWT
    const payload = {
      sub: email,
      iss: process.env.CLIENT_ID,
      jti: uuid(),
      iat: now,
      exp: expirationTime,
      account_type: accountType,
      teams: teamsArray,
      user_attributes: userAttributes,
      eval_connection_id: process.env[`${modePrefix}eval_connection_id`],
    };

    // Create signed JWT
    const token = jwt.sign(payload, process.env.SECRET, {
      algorithm: "HS256",
      keyid: process.env.CLIENT_ID,
    });

    // Build embed URL using base params and signed token
    const embedParams = [`:embed=true`, `:jwt=${encodeURIComponent(token)}`];

    // These parameters support sharing filtered state
    if (query.exploreKey) {
      embedParams.push(`:explore=${encodeURIComponent(query.exploreKey)}`);
    }
    if (query.bookmarkId) {
      embedParams.push(`:bookmark=${encodeURIComponent(query.bookmarkId)}`);
    }

    const signedEmbedUrl = `${baseUrl}?${embedParams.join("&")}`;

    // Append optional UI controls from .env
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

    // Debug logs (useful during development)
    console.log("Mode:", mode || "default");
    console.log("BASE_URL:", baseUrl); // use the looked-up baseUrl
    console.log("CLIENT_ID:", process.env.CLIENT_ID);
    console.log("SESSION_LENGTH:", process.env.SESSION_LENGTH);
    console.log("TEAMS:", teamsArray);
    console.log("ACCOUNT_TYPE:", accountType);
    console.log("Signed Embed URL:", signedEmbedUrl);

    console.log("[generateSignedUrl] Final Embed URL:", finalEmbedUrl);
    return { signedUrl: finalEmbedUrl, jwt: token };
  } catch (error) {
    console.error("Failed to generate JWT:", error.message);
    throw new Error("JWT generation failed");
  }
}

module.exports = { generateSignedUrl };
