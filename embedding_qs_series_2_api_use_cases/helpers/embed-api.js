const jwt = require("jsonwebtoken");
const { v4: uuid } = require("uuid");
const dotenv = require("dotenv");
const config = require("./config");

dotenv.config();

async function generateSignedUrl(mode = "", query = {}) {
  const embedType = query.embedType || "element";
  const now = Math.floor(Date.now() / 1000);
  const expirationTime =
    now + Math.min(parseInt(process.env.SESSION_LENGTH) || 3600, 2592000);
  const prefix = mode ? `${mode.toUpperCase()}_` : "";

  const email = process.env[`${prefix}EMAIL`] || process.env.EMAIL;
  const accountType =
    process.env[`${prefix}ACCOUNT_TYPE`] || process.env.ACCOUNT_TYPE;
  const rawTeams = process.env[`${prefix}TEAMS`] || process.env.TEAMS;

  const teams =
    rawTeams
      ?.split(",")
      .map((t) => t.trim())
      .filter(Boolean) || [];

  // User Attributes
  const userAttributes = {};
  for (const [key, val] of Object.entries(process.env)) {
    const attrPrefix = `${prefix}ua_`;
    if (key.startsWith(attrPrefix)) {
      userAttributes[key.slice(attrPrefix.length)] = val.trim();
    }
  }

  const payload = {
    sub: email,
    iss: process.env.CLIENT_ID,
    jti: uuid(),
    iat: now,
    exp: expirationTime,
    account_type: accountType,
    teams,
    user_attributes: userAttributes,
    eval_connection_id: process.env[`${prefix}eval_connection_id`] || undefined,
  };

  const token = jwt.sign(payload, process.env.SECRET, {
    algorithm: "HS256",
    keyid: process.env.CLIENT_ID,
  });

  // Dynamic target URL switching
  let baseUrl = "";

  if (embedType === "workbook") {
    baseUrl = process.env.EMBED_URL_WORKBOOK;
  } else if (embedType === "page") {
    baseUrl = process.env.EMBED_URL_PAGE;
  } else {
    baseUrl = process.env.EMBED_URL_ELEMENT;
  }

  if (!baseUrl) {
    throw new Error(`Missing EMBED_URL for embedType "${embedType}"`);
  }

  const params = [`:embed=true`, `:jwt=${encodeURIComponent(token)}`];
  if (query.exploreKey)
    params.push(`:explore=${encodeURIComponent(query.exploreKey)}`);
  if (query.bookmarkId)
    params.push(`:bookmark=${encodeURIComponent(query.bookmarkId)}`);

  const baseEmbedUrl = `${baseUrl}?${params.join("&")}`;


  const uiParams = [
    "disable_mobile_view",
    "hide_menu",
    "hide_folder_navigation",
    "hide_tooltip",
    "lng",
    "menu_position",
    "responsive_height",
    "theme",
  ];

  const uiQuery = uiParams
    .map((key) => {
      const val = process.env[key];
      return val ? `:${key}=${encodeURIComponent(val)}` : null;
    })
    .filter(Boolean)
    .join("&");

  const finalUrl = uiQuery ? `${baseEmbedUrl}&${uiQuery}` : baseEmbedUrl;

  // Debug logs
  console.log(`[generateSignedUrl] Mode: ${mode}`);
  console.log(`  Email: ${email}`);
  console.log(`  Account Type: ${accountType}`);
  console.log(`  Teams: ${teams.join(", ")}`);
  console.log(`  Final URL: ${finalUrl}`);

  return { signedUrl: finalUrl, jwt: token };
}

module.exports = { generateSignedUrl };
