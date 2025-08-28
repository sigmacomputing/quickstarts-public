// Title: Pagination
// Description: This script returns latest version, name and path for all workbooks.

// 1: Load environment variables from a specific .env file for configuration
require('dotenv').config({ path: 'recipes/.env' });

// 2: Import the function to obtain a bearer token from the authenticate-bearer module
const getBearerToken = require('./get-access-token');

// 3: Import Axios for making HTTP requests
const axios = require('axios');

// 4: Load use-case specific variables from environment variables
const baseURL = process.env.baseURL; // Your base URL
const limit = parseInt(process.env.LIMIT) || 100; // Number of results per page (max 1,000)
const maxPages = parseInt(process.env.MAX_PAGES) || 0; // Maximum pages to fetch (0 = all pages)

async function getAllWorkbooks() {
    let hasMore = true; // Initialize hasMore to true for the first request
    let nextPage = null; // Start from beginning
    let currentPage = 0; // Initialize currentPage counter
    let token = await getBearerToken(); // Obtain a bearer token for authentication

    
    if (!token) {
        console.error("Failed to obtain token, cannot proceed to fetch workbooks.");
        return; // Exit the function if token acquisition fails
    }

    if (maxPages > 0) {
        console.log(`Fetching up to ${maxPages} pages with ${limit} results per page`);
    } else {
        console.log(`Fetching all pages with ${limit} results per page`);
    }

    while (hasMore && (maxPages === 0 || currentPage < maxPages)) {
        try {
            currentPage++; // Increment the currentPage counter for each iteration
            // Construct URL with proper query parameters
            // Note: nextPage tokens from Sigma API are already URL-encoded
            let url = `${baseURL}/workbooks?limit=${limit}`;
            if (nextPage) {
                // Use the nextPage token as-is since it's already properly encoded
                url += `&page=${nextPage}`;
            }
            
            console.log(`Fetching page ${currentPage} from Sigma: ${url}`); // Log the constructed URL before sending the request

            const response = await axios.get(url, {
                headers: { Authorization: `Bearer ${token}` } // Authorization header with the bearer token
            });

            // Process current page workbooks for table display
            const entries = response.data.entries || [];
            const total = response.data.total || 'Unknown';
            
            console.log(`\nPage ${currentPage} Results (${entries.length} of ${total} total workbooks):`);
            console.log(`Has more pages: ${response.data.hasMore ? 'Yes' : 'No'}`);
            if (response.data.nextPage) {
                console.log(`Next page token: ${response.data.nextPage}`);
            }
            
            const workbooksForTable = entries.map((workbook, index) => ({
                "#": index + 1, // Sequence number within the current page
                Name: workbook.name, // Workbook name
                Path: workbook.path, // Workbook path
                LatestVersion: workbook.latestVersion // Latest version of the workbook
            }));

            console.table(workbooksForTable); // Display the current page workbooks in table format

            // Handle different possible response structures for pagination
            const apiHasMore = response.data.hasMore;
            const apiNextPage = response.data.nextPage;
            
            // If hasMore is undefined but nextPage exists, assume there are more pages
            // If hasMore is explicitly false, respect that
            if (apiHasMore === false) {
                hasMore = false;
            } else if (apiNextPage) {
                hasMore = true;
            } else {
                hasMore = false;
            }
            
            nextPage = apiNextPage;


        } catch (error) {
            console.error('Error fetching workbooks:', error);
            break; // Exit the loop in case of an error
        }
    }
}

getAllWorkbooks().catch(error => {
    console.error('Failed to fetch workbooks:', error);
});
