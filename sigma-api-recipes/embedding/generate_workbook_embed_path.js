// Load environment variables from a specific .env file for configuration
require('dotenv').config({ path: 'sigma-api-recipes/.env' });

// Import the function to obtain a bearer token from the authenticate-bearer module
const getBearerToken = require('../get-access-token');

// Import Axios for making HTTP requests
const axios = require('axios');

// Load use-case specific variables from environment variables
const baseURL = process.env.baseURL; // Base URL for the Sigma API - AWS US 
const memberId = process.env.MEMBERID; // The unique identifier of the member, used to fetch their specific workbooks

// Fetch List of Available Workbooks
// This function fetches the list of workbooks available to a specific member, filtering by type 'workbook'
async function fetchWorkbooks(memberId, accessToken) {
    const url = `${baseURL}/members/${memberId}/files?typeFilters=workbook`;
    console.log(`Fetching workbooks from: ${url}`); // Logs the constructed URL to console for verification
    try {
        const response = await axios.get(url, {
            headers: {
                'Authorization': `Bearer ${accessToken}`, // Uses the Bearer token for authorization
                'accept': 'application/json' // Specifies that the response should be in JSON format
            }
        });

        // Checks if 'entries' exists and is an array, then maps over it to return an array of workbook details
        if (response.data && Array.isArray(response.data.entries)) {
            return response.data.entries.map(workbook => ({
                id: workbook.urlId, // Extracts the urlId as id of the workbook
                name: workbook.name // Extracts the name of the workbook
            }));
        } else {
            console.error('No entries found or unexpected response structure:', response.data);
            return [];
        }
    } catch (error) {
        console.error(`Error fetching workbooks: ${error}`); // Logs errors if the API call fails
        if (error.response) {
            console.error(`Response status: ${error.response.status}`); // Logs the HTTP status code of the response
            console.error(`Response headers: ${JSON.stringify(error.response.headers)}`); // Logs the response headers
            console.error(`Response body: ${JSON.stringify(error.response.data, null, 2)}`); // Logs the response body
        } else {
            console.error(`Error details: ${error.message}`); // Logs details of errors not related to HTTP responses
        }
        return [];
    }
}

// Main function to manage the overall workflow
async function main() {
    const accessToken = await getBearerToken(); // Retrieves the access token
    if (!accessToken) {
        console.error('Failed to obtain Bearer token.'); // Logs an error if the token cannot be obtained
        return;
    }

    const workbooks = await fetchWorkbooks(memberId, accessToken); // Fetches workbooks using the member ID and access token
    if (workbooks.length > 0) {
        workbooks.forEach((workbook, index) => {
            const embedURL = `https://app.sigmacomputing.com/embed/1-CQjBrPzWu1JQiPaq2AfW2/workbook/${workbook.id}`;
            console.log(`#${index + 1}: ${workbook.name}: ${embedURL}`);
        });
    } else {
        console.log('No workbooks available for processing or embedding.'); // Logs a message if no workbooks are found
    }
}

if (require.main === module) {
    main(); // Executes the main function if the file is run directly
}

module.exports = main; // Exports the main function to allow it to be used in other modules