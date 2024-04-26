// This script provides permission to a connection, using the connectionId from .env

// 1: Load environment variables from a specific .env file for configuration
require('dotenv').config({ path: 'sigma-api-recipes/.env' });

// 2" Import the function to obtain a bearer token from the authenticate-bearer module
const getBearerToken = require('../get-access-token');

// 3: Import Axios for making HTTP requests
const axios = require('axios');

// 4: Load use-case specific variables from environment variables
const baseURL = process.env.baseURL; // Your base URL
const memberId = process.env.MEMBERID; // Retrieve the memberId, from .env
const connectionId = process.env.CONNECTIONID; // Retrieve the connectionId from .env

async function addNewConnectionPermission() {
    const accessToken = await getBearerToken();
    if (!accessToken) {
        console.error('Failed to obtain Bearer token.');
        return;
    }

    const requestURL = `${baseURL}/connections/${connectionId}/grants`; // Corrected URL structure
    console.log(`URL sent to Sigma: ${requestURL}`);

    try {
        // The 'grantee' structure might need adjustment based on Sigma's expected payload.
        const response = await axios.post(requestURL, {
            grants: [{
                grantee: { memberId: memberId }, // Specifies the member receiving the permission
                permission: 'usage' // Using "usage" since we created this user with as a Viewer in earlier steps
            }]
        }, {
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${accessToken}`
            }
        });

        console.log('New connection permission added successfully:', JSON.stringify(response.data, null, 2));
    } catch (error) {
        console.error('Error adding new connection permission:', error.response ? error.response.data : error.message);
    }
}

if (require.main === module) {
    addNewConnectionPermission();
}

module.exports = addNewConnectionPermission;
