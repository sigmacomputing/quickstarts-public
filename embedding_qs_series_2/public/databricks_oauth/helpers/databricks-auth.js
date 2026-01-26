// helpers/databricks-auth.js
// Databricks OAuth 2.0 authentication with PKCE support
// Handles authorization URL generation, token exchange, and token refresh

const axios = require('axios');
const { generatePKCE, generateState } = require('./pkce');

/**
 * Builds the Databricks OAuth authorization URL
 * @param {Object} config - Configuration object
 * @param {string} config.databricksHost - Databricks workspace URL
 * @param {string} config.accountId - Databricks account ID (for account-level auth)
 * @param {string} config.clientId - OAuth client ID
 * @param {string} config.redirectUri - OAuth redirect URI
 * @param {string} config.authLevel - 'workspace' or 'account'
 * @param {string} config.codeChallenge - PKCE code challenge
 * @param {string} config.state - CSRF state parameter
 * @returns {string} Authorization URL
 */
function getAuthorizationUrl(config) {
  const {
    databricksHost,
    accountId,
    clientId,
    redirectUri,
    authLevel,
    codeChallenge,
    state
  } = config;

  let baseUrl;

  if (authLevel === 'account') {
    // Account-level OAuth endpoint
    baseUrl = `https://accounts.azuredatabricks.net/oidc/accounts/${accountId}/v1/authorize`;
  } else {
    // Workspace-level OAuth endpoint
    // Remove trailing slash and protocol prefix if present
    const host = databricksHost.replace(/^https?:\/\//, '').replace(/\/$/, '');
    baseUrl = `https://${host}/oidc/v1/authorize`;
  }

  const params = new URLSearchParams({
    client_id: clientId,
    redirect_uri: redirectUri,
    response_type: 'code',
    state: state,
    code_challenge: codeChallenge,
    code_challenge_method: 'S256',
    scope: 'all-apis offline_access'
  });

  return `${baseUrl}?${params.toString()}`;
}

/**
 * Exchanges authorization code for access and refresh tokens
 * @param {Object} config - Configuration object
 * @param {string} config.databricksHost - Databricks workspace URL
 * @param {string} config.accountId - Databricks account ID (for account-level auth)
 * @param {string} config.clientId - OAuth client ID
 * @param {string} config.clientSecret - OAuth client secret
 * @param {string} config.redirectUri - OAuth redirect URI
 * @param {string} config.authLevel - 'workspace' or 'account'
 * @param {string} config.code - Authorization code from callback
 * @param {string} config.codeVerifier - PKCE code verifier
 * @returns {Promise<Object>} Token response with access_token, refresh_token, expires_in
 */
async function exchangeCodeForToken(config) {
  const {
    databricksHost,
    accountId,
    clientId,
    clientSecret,
    redirectUri,
    authLevel,
    code,
    codeVerifier
  } = config;

  let tokenEndpoint;

  if (authLevel === 'account') {
    tokenEndpoint = `https://accounts.azuredatabricks.net/oidc/accounts/${accountId}/v1/token`;
  } else {
    const host = databricksHost.replace(/^https?:\/\//, '').replace(/\/$/, '');
    tokenEndpoint = `https://${host}/oidc/v1/token`;
  }

  const params = new URLSearchParams({
    client_id: clientId,
    grant_type: 'authorization_code',
    code: code,
    redirect_uri: redirectUri,
    code_verifier: codeVerifier,
    scope: 'all-apis offline_access'
  });

  // Include client secret if provided (required for confidential clients)
  if (clientSecret) {
    params.append('client_secret', clientSecret);
  }

  try {
    const response = await axios.post(tokenEndpoint, params.toString(), {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded'
      }
    });

    console.log('[Databricks Auth] Token exchange successful');

    return {
      access_token: response.data.access_token,
      refresh_token: response.data.refresh_token,
      expires_in: response.data.expires_in,
      token_type: response.data.token_type,
      scope: response.data.scope
    };
  } catch (error) {
    console.error('[Databricks Auth] Token exchange failed:', error.response?.data || error.message);
    throw new Error(`Token exchange failed: ${error.response?.data?.error_description || error.message}`);
  }
}

/**
 * Refreshes an expired access token using a refresh token
 * @param {Object} config - Configuration object
 * @param {string} config.databricksHost - Databricks workspace URL
 * @param {string} config.accountId - Databricks account ID (for account-level auth)
 * @param {string} config.clientId - OAuth client ID
 * @param {string} config.clientSecret - OAuth client secret
 * @param {string} config.authLevel - 'workspace' or 'account'
 * @param {string} config.refreshToken - Refresh token
 * @returns {Promise<Object>} New token response
 */
async function refreshAccessToken(config) {
  const {
    databricksHost,
    accountId,
    clientId,
    clientSecret,
    authLevel,
    refreshToken
  } = config;

  let tokenEndpoint;

  if (authLevel === 'account') {
    tokenEndpoint = `https://accounts.azuredatabricks.net/oidc/accounts/${accountId}/v1/token`;
  } else {
    const host = databricksHost.replace(/^https?:\/\//, '').replace(/\/$/, '');
    tokenEndpoint = `https://${host}/oidc/v1/token`;
  }

  const params = new URLSearchParams({
    client_id: clientId,
    client_secret: clientSecret,
    grant_type: 'refresh_token',
    refresh_token: refreshToken
  });

  try {
    const response = await axios.post(tokenEndpoint, params.toString(), {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded'
      }
    });

    console.log('[Databricks Auth] Token refresh successful');

    return {
      access_token: response.data.access_token,
      refresh_token: response.data.refresh_token || refreshToken, // Some providers don't return new refresh token
      expires_in: response.data.expires_in,
      token_type: response.data.token_type,
      scope: response.data.scope
    };
  } catch (error) {
    console.error('[Databricks Auth] Token refresh failed:', error.response?.data || error.message);
    throw new Error(`Token refresh failed: ${error.response?.data?.error_description || error.message}`);
  }
}

/**
 * Gets current user information from Databricks
 * @param {string} accessToken - Databricks access token
 * @param {string} databricksHost - Databricks workspace URL
 * @returns {Promise<Object>} User information
 */
async function getCurrentUser(accessToken, databricksHost) {
  const host = databricksHost.replace(/^https?:\/\//, '').replace(/\/$/, '');
  const userEndpoint = `https://${host}/api/2.0/preview/scim/v2/Me`;

  try {
    const response = await axios.get(userEndpoint, {
      headers: {
        'Authorization': `Bearer ${accessToken}`
      }
    });

    console.log('[Databricks Auth] User info retrieved:', response.data.userName);

    return {
      email: response.data.userName,
      displayName: response.data.displayName,
      id: response.data.id
    };
  } catch (error) {
    console.error('[Databricks Auth] Failed to get user info:', error.response?.data || error.message);
    throw new Error(`Failed to get user info: ${error.message}`);
  }
}

module.exports = {
  getAuthorizationUrl,
  exchangeCodeForToken,
  refreshAccessToken,
  getCurrentUser,
  generatePKCE,
  generateState
};
