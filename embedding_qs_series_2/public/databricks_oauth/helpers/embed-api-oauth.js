// helpers/embed-api-oauth.js
// Sigma embedding with Databricks OAuth token encryption
// Generates signed embed URLs with connection-level OAuth tokens

const jwt = require('jsonwebtoken');
const { v4: uuid } = require('uuid');
const crypto = require('crypto');
const dotenv = require('dotenv');
const path = require('path');

// Load centralized .env file from parent directory
dotenv.config({ path: path.resolve(__dirname, '../../../.env') });

/**
 * Encrypts the Databricks OAuth token for secure embedding
 * Uses AES-256-CBC encryption with PKCS7 padding
 * @param {string} secret - Sigma embed secret
 * @param {string} token - Databricks access token
 * @returns {string} Encrypted token in format: iv:encrypted
 */
function encryptToken(secret, token) {
  // Derive a 32-byte key from the secret
  const key = crypto.createHash('sha256').update(secret).digest();

  // Generate random IV (initialization vector)
  const iv = crypto.randomBytes(16);

  // Create cipher
  const cipher = crypto.createCipheriv('aes-256-cbc', key, iv);

  // Encrypt the token
  let encrypted = cipher.update(token, 'utf8', 'base64');
  encrypted += cipher.final('base64');

  // Return IV + encrypted data (both base64 encoded)
  return `${iv.toString('base64')}:${encrypted}`;
}

/**
 * Generates a signed Sigma embed URL with Databricks OAuth token
 * @param {string} databricksAccessToken - Databricks OAuth access token
 * @param {string} userEmail - User's email address
 * @returns {Promise<{ signedUrl: string, jwt: string }>}
 */
async function generateSignedUrl(databricksAccessToken, userEmail) {
  try {
    const now = Math.floor(Date.now() / 1000);
    const sessionLength = parseInt(process.env.SESSION_LENGTH) || 3600;
    const expirationTime = now + Math.min(sessionLength, 2592000); // Max 30 days

    // Get configuration with support for QuickStart-specific overrides
    const sigmaClientId = process.env.CLIENT_ID;
    const sigmaSecret = process.env.SECRET;
    const baseUrl = process.env.DATABRICKS_OAUTH_BASE_URL;
    const connectionId = process.env.DATABRICKS_CONNECTION_ID;
    const email = userEmail || process.env.DATABRICKS_OAUTH_EMAIL || process.env.EMAIL;
    const accountType = process.env.DATABRICKS_OAUTH_ACCOUNT_TYPE || process.env.ACCOUNT_TYPE || 'View';
    const rawTeams = process.env.DATABRICKS_OAUTH_TEAMS || process.env.TEAMS || '';
    const teamsArray = rawTeams ? rawTeams.split(',').map(t => t.trim()) : [];

    // Validate required configuration
    if (!baseUrl) {
      throw new Error('DATABRICKS_OAUTH_BASE_URL not configured in .env file');
    }
    if (!connectionId) {
      throw new Error('DATABRICKS_CONNECTION_ID not configured in .env file');
    }

    // Encrypt the Databricks access token
    const encryptedToken = encryptToken(sigmaSecret, databricksAccessToken);

    console.log('[Embed API] Databricks token encrypted for connection:', connectionId);

    // Build JWT payload with encrypted OAuth token
    const payload = {
      sub: email,
      iss: sigmaClientId,
      jti: uuid(),
      iat: now,
      exp: expirationTime,
      account_type: accountType,
      teams: teamsArray,
      // Connection-level OAuth token
      connection_oauth_tokens: {
        [connectionId]: encryptedToken
      }
    };

    // Sign the JWT with Sigma secret
    const token = jwt.sign(payload, sigmaSecret, {
      algorithm: 'HS256',
      keyid: sigmaClientId
    });

    const embedParams = [
      ':embed=true',
      `:jwt=${encodeURIComponent(token)}`
    ];

    const signedEmbedUrl = `${baseUrl}?${embedParams.join('&')}`;

    console.log('[Embed API] Signed embed URL generated');
    console.log('[Embed API] User:', email);
    console.log('[Embed API] Account Type:', accountType);
    console.log('[Embed API] Teams:', teamsArray);

    return {
      signedUrl: signedEmbedUrl,
      jwt: token
    };
  } catch (error) {
    console.error('[Embed API] Failed to generate signed URL:', error.message);
    throw new Error('Failed to generate signed embed URL');
  }
}

/**
 * Decodes a JWT token without verification (for debugging)
 * @param {string} token - JWT token
 * @returns {Object} Decoded token payload
 */
function decodeJWT(token) {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) {
      throw new Error('Invalid JWT format');
    }

    const payload = JSON.parse(
      Buffer.from(parts[1], 'base64').toString('utf8')
    );

    return payload;
  } catch (error) {
    console.error('[Embed API] Failed to decode JWT:', error.message);
    return null;
  }
}

module.exports = {
  generateSignedUrl,
  encryptToken,
  decodeJWT
};
