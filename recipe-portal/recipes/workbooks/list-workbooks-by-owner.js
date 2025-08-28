// Title: List Workbooks by Owner
// Description: This script lists all workbooks owned by a specific member.

// Load environment variables from a specific .env file for configuration
require('dotenv').config({ path: 'recipes/.env' });

// Import the function to obtain a bearer token from the authenticate-bearer module
const getBearerToken = require('./get-access-token');

// Import Axios for making HTTP requests
const axios = require('axios');

// Load use-case specific variables from environment variables
const baseURL = process.env.baseURL; // Your base URL
const ownerId = process.env.MEMBERID; // Member ID to filter workbooks by owner

async function listWorkbooksByOwner() {
    const token = await getBearerToken();
    
    if (!token) {
        console.error("Failed to obtain token, cannot proceed to fetch workbooks.");
        return;
    }

    if (!ownerId) {
        console.error("MEMBERID is required to filter workbooks by owner.");
        return;
    }

    try {
        console.log(`Fetching workbooks owned by member: ${ownerId}`);
        
        // Construct URL with owner filter only
        const url = `${baseURL}/workbooks?ownerId=${ownerId}`;
        console.log(`Fetching from: ${url}`);

        const response = await axios.get(url, {
            headers: { Authorization: `Bearer ${token}` }
        });

        const workbooks = response.data.entries || [];
        console.log(`Found ${workbooks.length} workbooks owned by this member`);

        if (workbooks.length > 0) {
            // Display workbooks in table format
            const workbooksForTable = workbooks.map((workbook, index) => ({
                "#": index + 1,
                Name: workbook.name,
                Path: workbook.path || 'N/A',
                Created: workbook.createdAt ? new Date(workbook.createdAt).toLocaleDateString() : 'N/A',
                Modified: workbook.modifiedAt ? new Date(workbook.modifiedAt).toLocaleDateString() : 'N/A',
                Version: workbook.latestVersion || 'N/A',
                WorkbookId: workbook.workbookId
            }));

            console.table(workbooksForTable);
        } else {
            console.log("No workbooks found for this owner.");
        }

        console.log(`\\n📊 Summary: Found ${workbooks.length} workbooks owned by member ${ownerId}`);

    } catch (error) {
        console.error('Error fetching workbooks:', error.response ? error.response.data : error.message);
    }
}

// Execute the function
listWorkbooksByOwner().catch(error => {
    console.error('Failed to fetch workbooks:', error);
});