// helpers/provision.js

const axios = require('axios');
const getBearerToken = require('./get-access-token');
const config = require('../helpers/config');

const SIGMA_API_BASE = 'https://api.sigmacomputing.com/v2';

/**
 * Returns the memberId for a user with the given email (must already exist).
 */
async function lookupMemberId(email) {
  const token = await getBearerToken();
  const url = `${SIGMA_API_BASE}/users?email=${encodeURIComponent(email)}`;

  const response = await axios.get(url, {
    headers: { Authorization: `Bearer ${token}` }
  });

  const user = response.data?.data?.[0];
  if (!user || !user.id) throw new Error(`User not found: ${email}`);
  return user.id;
}

/**
 * Triggers auto-provisioning for an embed user and returns their memberId.
 */
async function provisionEmbedUser(email, accountType) {
  const token = await getBearerToken();
  
  const payload = {
    email,
    accountType,            // required for role (e.g., "Build" or "View")
    teams: ['Embed_Users'], // assign team membership
    embedPath: '/embed/blank',
    useExisting: true
  };

  const response = await axios.post(`${SIGMA_API_BASE}/embed/paths`, payload, {
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json'
    }
  });

  const memberId = response.data?.memberId;
  if (!memberId) throw new Error(`Failed to provision user: ${email}`);
  return memberId;
}

module.exports = {
  lookupMemberId,
  provisionEmbedUser
};
