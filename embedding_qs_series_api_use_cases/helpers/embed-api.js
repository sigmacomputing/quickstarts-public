// embed-api.js
// This module generates a signed Sigma embed URL using a shared configuration.

const jwt = require('jsonwebtoken');
const { v4: uuid } = require('uuid');
const {
  baseUrl,
  email,
  clientId,
  secret,
  sessionLength,
  accountType,
  teams,
  evalConnectionId,
  embedUiOptions
} = require('./config');

/**
 * Generate a signed Sigma embed URL using a shared configuration.
 *
 * @param {Object} [query={}] - Optional exploreKey/bookmarkId
 * @returns {Promise<{ signedUrl: string, jwt: string }>}
 */
async function generateSignedUrl(query = {}) {
  try {
    if (!baseUrl || !email || !clientId || !secret) {
      throw new Error("Missing required configuration values in .env");
    }

    const now = Math.floor(Date.now() / 1000);
    const expirationTime = now + Math.min(sessionLength, 2592000); // Max 30 days

    const userAttributes = {};
    for (const [key, value] of Object.entries(process.env)) {
      if (key.startsWith('ua_') && value) {
        const attrName = key.slice(3); // strip 'ua_'
        userAttributes[attrName] = value.trim();
      }
    }

    // Optional normalization for DRS_REGION
    const rawRegion = userAttributes.DRS_REGION?.trim().toUpperCase();
    const validRegions = ["DRS_EXECUTIVE", "DRS_WEST", "DRS_EAST", "DRS_DEFAULT"];
    if (rawRegion) {
      userAttributes.DRS_REGION = validRegions.includes(rawRegion) ? rawRegion : "DRS_DEFAULT";
    }

    // Build the JWT payload
    const payload = {
      sub: email,
      iss: clientId,
      jti: uuid(),
      iat: now,
      exp: expirationTime,
      account_type: accountType,
      teams,
      user_attributes: userAttributes,
      ...(evalConnectionId && { eval_connection_id: evalConnectionId })
    };

    const token = jwt.sign(payload, secret, {
      algorithm: 'HS256',
      keyid: clientId,
    });

    // Construct the base embed URL
    const baseEmbedUrl = `${baseUrl}?${[
      `:embed=true`,
      `:jwt=${encodeURIComponent(token)}`,
      query.exploreKey ? `:explore=${encodeURIComponent(query.exploreKey)}` : '',
      query.bookmarkId ? `:bookmark=${encodeURIComponent(query.bookmarkId)}` : ''
    ].filter(Boolean).join('&')}`;

    // Append optional UI flags
    const optionalQuery = Object.entries(embedUiOptions)
      .filter(([_, value]) => value !== undefined && value !== '')
      .map(([key, value]) => `:${key}=${encodeURIComponent(value)}`)
      .join('&');

    const finalUrl = optionalQuery ? `${baseEmbedUrl}&${optionalQuery}` : baseEmbedUrl;

    console.log('[generateSignedUrl] Final Embed URL:', finalUrl);
    return { signedUrl: finalUrl, jwt: token };
  } catch (err) {
    console.error('JWT generation failed:', err.message);
    throw err;
  }
}

// Export the function for use in other modules
module.exports = { generateSignedUrl };
