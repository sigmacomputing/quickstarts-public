// Title: Deactivate Existing Member
// Description: This script deactivates an existing member.

require('dotenv').config({ path: 'recipes/.env' });
const getBearerToken = require('../get-access-token');
const axios = require('axios');

const baseURL = process.env.baseURL;
const memberId = process.env.MEMBERID;

async function deleteMember() {
    const accessToken = await getBearerToken();
    if (!accessToken) {
        console.error('Failed to obtain Bearer token.');
        return;
    }

    const requestURL = `${baseURL}/members/${memberId}`;

    try {
        console.log(`URL sent to Sigma: ${requestURL}`);

        // Note: Axios delete method does not need to pass memberId as data in the body for this operation
        const response = await axios.delete(requestURL, {
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                // 'Content-Type': 'application/json' is not necessary for a delete operation without a body
            }
        });

        console.log('Member deleted successfully:', JSON.stringify(response.data, null, 2));
    } catch (error) {
        console.error('Error deleting member:', error.response ? error.response.data : error.message);
    }
}

deleteMember();
