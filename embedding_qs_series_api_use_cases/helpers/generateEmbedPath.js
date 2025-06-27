// generateEmbedPath.js
// This module generates a secure embed path for a Sigma workbook by impersonating a user.

const axios = require('axios');
const getValidToken = require('./auth');
require('dotenv').config();

// Ensure required environment variables are set.
const SIGMA_API = 'https://api.sigmacomputing.com';
const WORKBOOK_ID = process.env.WORKBOOK_ID; // Add this to your .env

/**
 * Generate a secure embed path by impersonating a Sigma user
 * @param {string} memberId - Sigma member ID of the user to impersonate
 * @returns {Promise<string|null>} - Secure embed path or null on failure
 */
// @throws {Error} If WORKBOOK_ID is not set in .env
async function generateEmbedPath(memberId) {
  if (!WORKBOOK_ID) {
    throw new Error('WORKBOOK_ID is not set in .env');
  }
// Validate memberId
  try {
    const token = await getValidToken();
// Check if token is valid
    const response = await axios.post(
      `${SIGMA_API}/v2/embed/paths`,
      {
        embedType: 'secure',
        sourceType: 'workbook',
        sourceId: WORKBOOK_ID,
        memberId: memberId,
      },
      {
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        }
      }
    );

    // Check if the response contains the expected path
    const path = response.data.path;
    console.log(`Embed path for member ${memberId}: ${path}`);
    return path;
  } catch (err) {
    console.error('Failed to generate embed path:', err.response?.data || err.message);
    return null;
  }
}
// This function generates a secure embed path for a Sigma workbook by impersonating a user.
module.exports = generateEmbedPath;
