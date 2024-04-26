// This script lists all workbooks, returning name, URL, URL ID, and version

// 1: Load environment variables from a specific .env file for configuration
require('dotenv').config({ path: 'rest-api-recipes/.env' });

// 2: Import the function to obtain a bearer token from the authenticate-bearer module
const getBearerToken = require('../get-access-token');

// 3: Import Axios for making HTTP requests
const axios = require('axios');

// 4: Load use-case specific variables from environment variables
const baseURL = process.env.baseURL; // Your base URL

// Define an asynchronous function to fetch workbooks with pagination
async function fetchWorkbooksWithPagination(url, accessToken) {
    let results = [];
    let nextPageToken = ''; // Initialize pagination token
    do {
        const fullUrl = `${url}${nextPageToken ? `?page=${nextPageToken}` : ''}`;
        console.log(`Fetching: ${fullUrl}`);
        try {
            const response = await axios.get(fullUrl, {
                headers: { 'Authorization': `Bearer ${accessToken}` },
            });
            results = [...results, ...response.data.entries];
            nextPageToken = response.data.nextPage; // Update the nextPageToken with the next page value
        } catch (error) {
            console.error(`Error fetching workbooks: ${error}`);
            break; // Exit loop on error
        }
    } while (nextPageToken); // Continue fetching pages until there's no nextPageToken
    return results;
}

// Define an asynchronous function to list workbooks
async function listWorkbooks() {
    const accessToken = await getBearerToken();
    if (!accessToken) {
        console.error('Failed to obtain Bearer token.');
        return;
    }

    try {
        // Fetch all workbooks with pagination
        const workbooks = await fetchWorkbooksWithPagination(`${baseURL}/workbooks`, accessToken);

        if (workbooks.length > 0) {
            // Display information for each workbook
            workbooks.forEach((workbook, index) => {
                console.log(`#${index + 1}: Name: ${workbook.name}, URL: ${workbook.url}, URL ID: ${workbook.workbookUrlId}, Latest Version: ${workbook.latestVersion}`);
            });
        } else {
            console.log('No workbooks found.');
        }
    } catch (error) {
        console.error('Error listing workbooks:', error);
    }
}

// Execute the function to list workbooks if this script is run directly
if (require.main === module) {
    listWorkbooks();
}

// Export the listWorkbooks function for reuse in other modules
module.exports = listWorkbooks;