// Title: All Input Tables
// Description: This script lists all instances of input-tables, across all workbooks, where they exist.
// Utilizes Sigma's API as documented in their Swagger documentation.

// Load necessary dependencies and set up the environment
require('dotenv').config({ path: 'recipes/.env' }); // Load environment variables for configuration
const getBearerToken = require('./get-access-token'); // Import function to obtain a bearer token for API authentication
const axios = require('axios'); // Import Axios for making HTTP requests

const baseURL = process.env.baseURL; // Load the base URL for API requests from environment variables

// Handle any unhandled promise rejections to prevent the script from failing silently
process.on('unhandledRejection', error => {
    console.error('Unhandled promise rejection:', error);
});

// Function to fetch and log details of 'input-table' elements within a specific workbook
async function fetchElementsOfWorkbook(workbook, accessToken) {
    try {
        // Fetch all pages within the workbook
        const pagesResponse = await axios.get(`${baseURL}/workbooks/${workbook.workbookId}/pages`, {
            headers: { 'Authorization': `Bearer ${accessToken}` }, // Include the authorization header
        });

        // Iterate through each page in the workbook
        for (const page of pagesResponse.data.entries) {
            const elementsUrl = `${baseURL}/workbooks/${workbook.workbookId}/pages/${page.pageId}/elements`; // Construct the URL to fetch elements
            try {
                // Fetch elements for the current page
                const elementsResponse = await axios.get(elementsUrl, {
                    headers: { 'Authorization': `Bearer ${accessToken}` }, // Include the authorization header
                });
        
                // Filter for elements of type 'input-table'
                const inputTableElements = elementsResponse.data.entries.filter(element => element.type === 'input-table');
                if (inputTableElements.length > 0) {
                    // Log workbook and page details if 'input-table' elements are found
                    console.log(`Workbook: "${workbook.name}", Path: "${workbook.path}/${workbook.workbookId}", Page: "${page.name}"`);
                    inputTableElements.forEach(element => {
                        // Log details for each 'input-table' element
                        console.log(`  - Input Table: ${element.name}, Element ID: ${element.elementId}, Latest Version: ${workbook.latestVersion}`);
                    });
                }
            } catch (error) {
                console.error(`Error fetching elements for page "${page.name}" in workbook "${workbook.name}":`, error.response ? error.response.data : error.message);
            }
        }
    } catch (error) {
        console.error(`Error fetching pages for workbook "${workbook.name}":`, error.response ? error.response.data : error.message);
    }
}

// Main function to list workbooks and find 'input-table' elements within them
async function listWorkbooksAndFindInputTables() {
    console.log('Starting to search for input-table elements across all workbooks...');
    const accessToken = await getBearerToken(); // Obtain the bearer token for API authentication
    if (!accessToken) {
        console.error('Failed to obtain Bearer token.'); // Log an error if the token cannot be obtained
        return;
    }

    try {
        // Fetch all workbooks accessible to the token
        const workbooksResponse = await axios.get(`${baseURL}/workbooks`, {
            headers: { 'Authorization': `Bearer ${accessToken}` }, // Include the authorization header
        });

        // Iterate through each workbook to search for 'input-table' elements
        for (const workbook of workbooksResponse.data.entries) {
            await fetchElementsOfWorkbook(workbook, accessToken); // Process each workbook
        }
    } catch (error) {
        console.error('Error fetching workbooks:', error.response ? error.response.data : error.message);
    }
    console.log('Completed searching for input-table elements.'); // Indicate completion of the script
}

// Execute the main function if the script is run directly
if (require.main === module) {
    listWorkbooksAndFindInputTables();
}

// Export the main function for use in other modules
module.exports = listWorkbooksAndFindInputTables;