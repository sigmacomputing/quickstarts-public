// helpers/generateEmbedPath.js
const axios = require('axios');
const getValidToken = require('./auth');
require('dotenv').config();

const SIGMA_API = 'https://api.sigmacomputing.com';
const WORKBOOK_ID = process.env.WORKBOOK_ID;
const VIEW_MEMBER_ID = process.env.VIEW_MEMBER_ID;
const BUILD_MEMBER_ID = process.env.BUILD_MEMBER_ID;

// Log environment variables for debugging only
console.log("ENV: VIEW_MEMBER_ID =", VIEW_MEMBER_ID);
console.log("ENV: BUILD_MEMBER_ID =", BUILD_MEMBER_ID);

/**
 * Generate a secure embed path by impersonating a Sigma user
 * @param {string} accountTypeOrId - 'view', 'build', or a literal memberId
 * @returns {Promise<string|null>} - Secure embed path or null on failure
 */
async function generateEmbedPath(accountTypeOrId) {
  if (!WORKBOOK_ID) {
    throw new Error("WORKBOOK_ID is not set in .env");
  }

  const memberId = {
    view: VIEW_MEMBER_ID,
    build: BUILD_MEMBER_ID,
  }[accountTypeOrId?.toLowerCase()] || accountTypeOrId;

  console.log("Resolved memberId for", accountTypeOrId, "→", memberId);

  if (!memberId) {
    throw new Error(`Invalid or missing memberId for selected role: ${accountTypeOrId}`);
  }

  try {
    const token = await getValidToken();
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

    const path = response.data?.path;
    console.log(`Embed path for ${accountTypeOrId} (${memberId}): ${path}`);
    return path;
  } catch (err) {
    console.error('Failed to generate embed path:', err.response?.data || err.message);
    return null;
  }
}

module.exports = generateEmbedPath;
