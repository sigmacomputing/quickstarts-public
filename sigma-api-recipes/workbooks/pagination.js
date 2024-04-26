// This script will return specified fields for all workbooks, using pagination and format the response as a table.

// 1: Load environment variables from a specific .env file for configuration
require('dotenv').config({ path: 'sigma-api-recipes/.env' });

// 2: Import the function to obtain a bearer token from the authenticate-bearer module
const getBearerToken = require('../get-access-token');

// 3: Import Axios for making HTTP requests
const axios = require('axios');

// 4: Load use-case specific variables from environment variables
const baseURL = process.env.baseURL; // Your base URL

async function getAllWorkbooks() {
    let hasMore = true; // Initialize hasMore to true for the first request
    let nextPage = ''; // Initialize nextPage with an empty string for the first request
    let currentPage = 0; // Initialize currentPage counter
    let token = await getBearerToken(); // Obtain a bearer token for authentication

    
    if (!token) {
        console.error("Failed to obtain token, cannot proceed to fetch workbooks.");
        return; // Exit the function if token acquisition fails
    }

    while (hasMore) {
        try {
            currentPage++; // Increment the currentPage counter for each iteration
            const url = `${baseURL}/workbooks${nextPage ? '?page=' + nextPage : ''}`;
            console.log(`Fetching page ${currentPage} from Sigma: ${url}`); // Log the constructed URL before sending the request

            const response = await axios.get(url, {
                headers: { Authorization: `Bearer ${token}` } // Authorization header with the bearer token
            });

            // Process current page workbooks for table display
            console.log(`Workbooks on Page ${currentPage}:`);
            const workbooksForTable = response.data.entries.map((workbook, index) => ({
                "#": index + 1, // Sequence number within the current page
                Name: workbook.name, // Workbook name
                Path: workbook.path, // Workbook path
                LatestVersion: workbook.latestVersion // Latest version of the workbook
            }));

            console.table(workbooksForTable); // Display the current page workbooks in table format

            hasMore = response.data.hasMore; // Update hasMore based on the response
            nextPage = response.data.nextPage; // Update nextPage token/value for pagination

        } catch (error) {
            console.error('Error fetching workbooks:', error);
            break; // Exit the loop in case of an error
        }
    }
}

getAllWorkbooks().catch(error => {
    console.error('Failed to fetch workbooks:', error);
});
