// Title: Get Workbooks Name, Version and URL
// Description: This script lists all workbook names, URLs, and version numbers in tabular form.
// Swagger: https://help.sigmacomputing.com/reference/listworkbooks-1

// 1: Load environment variables from a specific .env file for configuration
require('dotenv').config({ path: 'recipes/.env' });

// 2: Import the function to obtain a bearer token from the authenticate-bearer module
const getBearerToken = require('./get-access-token');

// 3: Import Axios for making HTTP requests
const axios = require('axios');

// 4: Load use-case specific variables from environment variables
const baseURL = process.env.baseURL; // Your base URL

// Function to fetch workbooks with pagination support
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

// Main function to list workbooks
async function listWorkbooks() {
    const accessToken = await getBearerToken();
    if (!accessToken) {
        console.error('Failed to obtain Bearer token.');
        return;
    }

    // Fetch all workbooks with pagination support
    const workbooks = await fetchWorkbooksWithPagination(`${baseURL}/workbooks`, accessToken);

    if (workbooks.length > 0) {
        // Prepare the data for display in a table format
        const workbooksForTable = workbooks.map((workbook, index) => ({
            Name: workbook.name, // Use the names directly
            URL: workbook.url, // URL for the workbook
            Version: workbook.latestVersion // Latest version of the workbook
        }));

        // Display the prepared data as a table in the console
        console.table(workbooksForTable);
    } else {
        console.log('No workbooks found.');
    }
}

// Execute the listWorkbooks function if running as the main module
if (require.main === module) {
    listWorkbooks();
}

module.exports = listWorkbooks;
