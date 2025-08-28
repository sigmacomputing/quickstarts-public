// Title: List All Workbooks with Details
// Description: This script lists all workbooks, returning name, URL, URL ID, and version.
//
// PREREQUISITES:
// - Valid authentication credentials required
// - User must have appropriate permissions to list workbooks
// - For large organizations: Results are paginated, use LIMIT and MAX_PAGES parameters to control output

// 1: Load environment variables from a specific .env file for configuration
require('dotenv').config({ path: '../../../sigma-api-recipes/.env' });

// 2: Import the function to obtain a bearer token from the authenticate-bearer module
const getBearerToken = require('../get-access-token');

// 3: Import Axios for making HTTP requests
const axios = require('axios');

// 4: Load necessary modules for file handling
const fs = require('fs');
const path = require('path');

// 5: Load use-case specific variables from environment variables
const baseURL = process.env.baseURL; // Your base URL
const limit = parseInt(process.env.LIMIT) || 100000; // Maximum workbooks to retrieve (Default: 100,000 | Max: 1,000,000)
const maxLimit = 1000000;

// Define an asynchronous function to fetch workbooks with pagination
async function fetchWorkbooksWithPagination(url, accessToken) {
    // Validate row limit
    if (limit > maxLimit) {
        actualLimit = maxLimit;
    } else {
        actualLimit = limit;
    }
    
    let results = [];
    let nextPageToken = ''; // Initialize pagination token
    let pageNum = 0;
    do {
        pageNum++;
        const fullUrl = url + (nextPageToken ? '?page=' + nextPageToken : '');
        console.log('Fetching page ' + pageNum + '...');
        try {
            const response = await axios.get(fullUrl, {
                headers: { 'Authorization': 'Bearer ' + accessToken },
            });
            results = [...results, ...response.data.entries];
            
            console.log('Found ' + response.data.entries.length + ' workbooks on page ' + pageNum);
            
            // Check if we've reached the limit
            if (results.length >= actualLimit) {
                results = results.slice(0, actualLimit);
                break;
            }
            
            nextPageToken = response.data.nextPage; // Update the nextPageToken with the next page value
        } catch (error) {
            console.log('Error fetching workbooks: ' + error.message);
            break; // Exit loop on error
        }
    } while (nextPageToken); // Continue fetching pages until there's no nextPageToken
    return results;
}

// Define an asynchronous function to list workbooks
async function listWorkbooks() {
    try {
        console.log('Authenticating...');
        const accessToken = await getBearerToken();
        if (!accessToken) {
            console.log('ERROR: Authentication failed');
            return;
        }
        console.log('Authentication successful');

        console.log('Fetching workbooks (limit: ' + limit + ')...');
        // Fetch all workbooks with pagination
        const workbooks = await fetchWorkbooksWithPagination(`${baseURL}/workbooks`, accessToken);

        if (workbooks.length > 0) {
            console.log('Found ' + workbooks.length + ' workbooks:');
            console.log('');
            
            // Display detailed information for each workbook in a clean format
            workbooks.forEach((workbook, index) => {
                console.log('=== Workbook #' + (index + 1) + ' ===');
                console.log('Name: ' + (workbook.name || 'Unknown'));
                console.log('URL: ' + (workbook.url || 'No URL'));
                console.log('URL ID: ' + (workbook.workbookUrlId || 'No URL ID'));
                console.log('Path: ' + (workbook.path || 'No path'));
                console.log('Latest Version: ' + (workbook.latestVersion || 'Unknown'));
                console.log('Created: ' + (workbook.createdAt ? new Date(workbook.createdAt).toLocaleDateString() : 'Unknown'));
                console.log('Updated: ' + (workbook.updatedAt ? new Date(workbook.updatedAt).toLocaleDateString() : 'Unknown'));
                console.log('Owner ID: ' + (workbook.ownerId || 'Unknown'));
                console.log('');
            });
            
            console.log('=== SUMMARY ===');
            console.log('Total Workbooks: ' + workbooks.length);
            console.log('Export completed successfully');
            
            // Brief delay before exit to allow UI to process the completion
            setTimeout(() => {
                process.exit(0);
            }, 2000);
        } else {
            console.log('No workbooks found.');
        }
    } catch (error) {
        console.log('FATAL ERROR: ' + error.message);
    }
}

// Execute the function to list workbooks if this script is run directly
if (require.main === module) {
    listWorkbooks();
}

// Export the listWorkbooks function for reuse in other modules
module.exports = listWorkbooks;