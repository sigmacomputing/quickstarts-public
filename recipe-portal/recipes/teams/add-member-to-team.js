// Title: Add Member to Team
// Description: This script adds a member to a team.

require('dotenv').config({ path: 'recipes/.env' });

const getBearerToken = require('../get-access-token');
const axios = require('axios');

const baseURL = process.env.baseURL; // Your base URL
const memberId = process.env.MEMBERID; // The unique identifier of the member you're adding to the team
const teamId = process.env.TEAMID; // The unique identifier of the team

async function addMemberToTeam() {
    const accessToken = await getBearerToken();
    if (!accessToken) {
        console.error('Failed to obtain Bearer token.');
        return;
    }

    const requestURL = `${baseURL}/teams/${teamId}/members`;
    console.log(`URL sent to Sigma: ${requestURL}`);

    try {
        // Adjusting for the PATCH request and format based on the curl example
        const response = await axios.patch(requestURL, {
            add: [memberId] // The memberId should be in an array
        }, {
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${accessToken}`
            }
        });

        console.log('Member successfully added to team:', JSON.stringify(response.data, null, 2));
    } catch (error) {
        console.error('Error adding member to team:', error.response ? JSON.stringify(error.response.data, null, 2) : error.message);
    }
}

if (require.main === module) {
    addMemberToTeam();
}

module.exports = addMemberToTeam;
