// Load environment variables from a specific .env file for configuration
require('dotenv').config({ path: 'sigma-api-recipes/.env' });

// Import the function to obtain a bearer token from the authenticate-bearer module
const getBearerToken = require('../get-access-token');

// Import Axios for making HTTP requests
const axios = require('axios');
const fs = require('fs'); // Import File System for saving output

// Load use-case specific variables from environment variables
const baseURL = process.env.baseURL; // Your base URL
const limit = process.env.LIMIT || 200; // Get limit from .env, default to 200

// Define an asynchronous function to list members.
async function listMembers() {
    // Obtain a bearer token using the previously imported function.
    const accessToken = await getBearerToken();
    if (!accessToken) {
        console.log('Failed to obtain Bearer token.');
        return;
    }

    let allMembers = [];  // Store all retrieved members
    let nextPage = null;  // Initialize pagination token

    try {
        while (true) {
            // Construct the API URL with pagination
            let membersURL = `${baseURL}/members?limit=${limit}`;
            if (nextPage) {
                membersURL += `&page=${encodeURIComponent(nextPage)}`;
            }

            console.log(`Fetching members from: ${membersURL}`);

            // Make API request
            const response = await axios.get(membersURL, {
                headers: {
                    'Authorization': `Bearer ${accessToken}`,
                    'Accept': 'application/json'
                }
            });

            // Check if API response contains entries
            const members = response.data.entries || [];
            console.log(`Fetched ${members.length} members in this batch.`);

            // Append fetched members to allMembers
            allMembers = allMembers.concat(members);
            console.log(`Total members collected so far: ${allMembers.length}`);

            // Check if there's a nextPage token
            nextPage = response.data.nextPage || null;
            if (!nextPage) break; // Stop if there are no more pages
        }

        console.log(`Total Members Retrieved: ${allMembers.length}`);

        // Save to a JSON file for verification
        fs.writeFileSync('members_output.json', JSON.stringify(allMembers, null, 2));
        console.log("Full member list saved to members_output.json");

    } catch (error) {
        console.error('Error listing members:', error.response ? error.response.data : error);
    }
}

// Execute the function to list members.
listMembers();
