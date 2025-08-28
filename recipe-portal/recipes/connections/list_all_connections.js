// Title: List All Connections
// Description: This script lists all connections in alphabetically order by name

// Load environment variables from a specific .env file for configuration
require('dotenv').config({ path: 'recipes/.env' });

// Import the function to obtain a bearer token from the authenticate-bearer module
const getBearerToken = require('../get-access-token');

// Import Axios for making HTTP requests
const axios = require('axios');

// Load use-case specific variables from environment variables
const baseURL = process.env.baseURL; // Your base URL

// Define an asynchronous function to fetch and sort connections
async function listConnections() {
    const accessToken = await getBearerToken();
    if (!accessToken) {
        console.error('Failed to obtain Bearer token.');
        return;
    }

    try {
        const endpoint = `${baseURL}/connections?includeArchived=false`;
        console.log(`Fetching connections from: ${endpoint}`);

        // API request to fetch connections
        const response = await axios.get(endpoint, {
            headers: { 'Authorization': `Bearer ${accessToken}`, 'Accept': 'application/json' },
        });

        const connections = response.data.entries; // Access 'entries' field in response

        console.log('Raw Response:', response.data); // Debugging log to confirm data structure

        if (connections && connections.length > 0) {
            // Sort connections alphabetically by name
            const sortedConnections = connections.sort((a, b) =>
                a.name.localeCompare(b.name)
            );

            // Display sorted connections
            sortedConnections.forEach((connection, index) => {
                console.log(`#${index + 1}: Name: ${connection.name}, ID: ${connection.connectionId}, Type: ${connection.type}`);
            });
        } else {
            console.log('No connections found.');
        }
    } catch (error) {
        console.error('Error fetching connections:', error.message);
        if (error.response) {
            console.error('Response Data:', error.response.data);
        }
    }
}

// Execute the function to list connections if this script is run directly
if (require.main === module) {
    listConnections();
}

// Export the listConnections function for reuse in other modules
module.exports = listConnections;
