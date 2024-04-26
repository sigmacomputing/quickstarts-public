// This script creates a new workspace, named using the memberId from .env

// 1: Load environment variables from a specific .env file for configuration
require('dotenv').config({ path: 'sigma-api-recipes/.env' });

// 2" Import the function to obtain a bearer token from the authenticate-bearer module
const getBearerToken = require('../get-access-token');

// 3: Import Axios for making HTTP requests
const axios = require('axios');

// 4: Load use-case specific variables from environment variables
const baseURL = process.env.baseURL; // Your base URL
const memberId = process.env.MEMBERID; // Retrieve the memberId to create a workspace for

async function addNewWorkspace() {
    const accessToken = await getBearerToken();
    if (!accessToken) {
        console.error('Failed to obtain Bearer token.');
        return;
    }

    const workspaceName = `Workspace for Member ${memberId}`; // Descriptive but unique workspace name
    const requestURL = `${baseURL}/workspaces`;
    console.log(`URL sent to Sigma: ${requestURL}`);

    try {
        const response = await axios.post(requestURL, {
            name: workspaceName // Corrected to lowercase 'n', which is the common convention
        }, {
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${accessToken}`
            }
        });

        console.log('New workspace added successfully:', JSON.stringify(response.data, null, 2));
    } catch (error) {
        console.error('Error adding new workspace:', error.response ? error.response.data : error.message);
    }
}

if (require.main === module) {
    addNewWorkspace();
}

module.exports = addNewWorkspace;
