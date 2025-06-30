const axios = require("axios");
const getBearerToken = require("./get-access-token");
const config = require("../helpers/config");

const SIGMA_API_BASE = config.apiBaseUrl;
const teamIdCache = {}; // In-memory cache for team IDs

/**
 * Look up a team ID by name, using cache if available.
 */
async function getTeamIdByName(teamName) {
  if (teamIdCache[teamName]) {
    console.log(`Returning cached team ID for "${teamName}"`);
    return teamIdCache[teamName];
  }

  const token = await getBearerToken();
  const url = `${SIGMA_API_BASE}/teams?name=${encodeURIComponent(teamName)}`;

  try {
    const response = await axios.get(url, {
      headers: { Authorization: `Bearer ${token}` },
    });

    const team = response.data?.entries?.[0];
    if (!team || !team.teamId) throw new Error(`Team not found: ${teamName}`);
    console.log(`Found team "${teamName}" → ${team.teamId}`);
    teamIdCache[teamName] = team.teamId;
    return team.teamId;

    return team.id;
  } catch (err) {
    console.error(`getTeamIdByName failed for ${teamName}`);
    if (err.response) {
      console.error("Status:", err.response.status);
      console.error("Message:", err.response.data?.message);
      console.error("Request ID:", err.response.data?.requestId);
    } else {
      console.error("Unknown error:", err.message);
    }
    throw err;
  }
}

/**
 * Look up an existing member by email.
 */
async function lookupMemberId(email) {
  const token = await getBearerToken();
  const url = `${SIGMA_API_BASE}/members?search=${encodeURIComponent(email)}`;

  try {
    const response = await axios.get(url, {
      headers: { Authorization: `Bearer ${token}` },
    });

    const member = response.data?.entries?.[0];
    if (!member || !member.memberId)
      throw new Error(`Member not found: ${email}`);

    console.log(`Found member ${email} → ${member.memberId}`);
    return member.memberId;
  } catch (err) {
    console.error(`lookupMemberId failed for ${email}`);
    if (err.response) {
      console.error("Status:", err.response.status);
      console.error("Message:", err.response.data?.message);
      console.error("Request ID:", err.response.data?.requestId);
    } else {
      console.error("Unknown error:", err.message);
    }
    throw err;
  }
}

/**
 * Provision a new embed user and assign to Embed_Users team.
 */
async function provisionEmbedUser(email, firstName, lastName, memberType) {
  const token = await getBearerToken();
  const teamId = await getTeamIdByName("Embed_Users");

  const payload = {
    userKind: "embed",
    memberType,
    email,
    firstName,
    lastName,
    addToTeams: [{ teamId, isTeamAdmin: false }],
    isGuest: false,
  };

  try {
    const response = await axios.post(
      `${SIGMA_API_BASE}/members?sendInvite=false`,
      payload,
      {
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      }
    );

    console.log(
      "Full response from /members:",
      JSON.stringify(response.data, null, 2)
    );

    const memberId = response.data?.id;
    if (!memberId)
      throw new Error(`Provisioning failed: no member ID returned`);

    console.log(`Provisioned ${email} → memberId: ${memberId}`);
    return memberId;
  } catch (err) {
    if (err.response?.status === 409) {
      const msg = err.response.data?.message || "";
      const match = msg.match(/member-id=([\w-]+)/);
      const existingId = match?.[1];
      if (existingId) {
        console.warn(`Member already exists: ${email} → ${existingId}`);
        return existingId;
      }
    }

    console.error(`provisionEmbedUser failed for ${email}`);
    if (err.response) {
      console.error("Status:", err.response.status);
      console.error("Message:", err.response.data?.message);
      console.error("Request ID:", err.response.data?.requestId);
    } else {
      console.error("Unknown error:", err.message);
    }
    throw err;
  }
}

module.exports = {
  lookupMemberId,
  provisionEmbedUser,
  getTeamIdByName, 
};
