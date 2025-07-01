// auth.js
// This module handles authentication by caching the bearer token and refreshing it when necessary.

const getBearerToken = require('./get-access-token');

// Cached token and expiry time
let cachedToken = null;
let tokenExpiry = null;

// Function to get a valid bearer token, refreshing it if necessary
async function getValidToken() {
  const now = Math.floor(Date.now() / 1000);

    // Check if we have a cached token and if it's still valid
  if (!cachedToken || now >= tokenExpiry) {
    console.log('🔄 Refreshing bearer token...');
    const token = await getBearerToken();
    if (!token) throw new Error('Failed to obtain bearer token');
    
    // Store the new token and set its expiry
    cachedToken = token;

    // Decode token (JWT) to get expiration, or set expiry +1 hour as default
    const [, payload] = token.split('.');
    const decoded = JSON.parse(Buffer.from(payload, 'base64').toString());
    tokenExpiry = decoded.exp || now + 3600;

    // Ensure expiry is at least 1 hour from now
    console.log('Bearer token refreshed and valid until', new Date(tokenExpiry * 1000).toISOString());
  } else {
    // If we have a cached token, just log its expiry
    console.log('Using cached bearer token, expires at', new Date(tokenExpiry * 1000).toISOString());
  }

  // Return the cached token
  return cachedToken;
}

// Export the function to get a valid token
module.exports = getValidToken;
