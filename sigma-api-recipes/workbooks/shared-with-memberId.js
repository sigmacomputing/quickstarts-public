// This script lists all workbook names, URLs, and version numbers for the specified memberId

// 1: Load environment variables from a specific .env file for configuration
require('dotenv').config({ path: 'sigma-api-recipes/.env' });

// 2: Import the function to obtain a bearer token from the authenticate-bearer module
const getBearerToken = require('../get-access-token');

// 3: Import Axios for making HTTP requests
const axios = require('axios');

// 4: Load use-case specific variables from environment variables
const baseURL = process.env.baseURL; // Your base URL
const memberId = process.env.MEMBERID; // Retrieve the memberId from .env

// Function to fetch all items with limit = 500
async function fetchMemberFiles(memberId, accessToken) {
    try {
        const fullUrl = `${baseURL}/members/${memberId}/files?typeFilters=workbook&limit=500`;
        console.log(`Fetching member files: ${fullUrl}`);
        const response = await axios.get(fullUrl, {
            headers: {
                'Authorization': `Bearer ${accessToken}`,
            },
        });

        return response.data.entries;
    } catch (error) {
        console.error('Error fetching member files:', error);
        return [];
    }
}

// Main function to list workbooks accessible to a specific member
async function listAccessibleWorkbooks() {
    const accessToken = await getBearerToken();
    if (!accessToken) return;

    try {
        // Fetching all URL IDs from the member's files
        const memberFiles = await fetchMemberFiles(memberId, accessToken);
        const memberFileIds = memberFiles.map(file => file.id);

        // Fetching all workbooks with a manual limit of 200 rows
        const workbooksUrl = `${baseURL}/workbooks?limit=200`;
        const response = await axios.get(workbooksUrl, {
            headers: {
                'Authorization': `Bearer ${accessToken}`,
            },
        });
        const allWorkbooks = response.data.entries;

        // Filtering workbooks accessible to the member
        const accessibleWorkbooks = allWorkbooks.filter(workbook => {
            // Check if the workbookId is in the member's file IDs
            return memberFileIds.includes(workbook.workbookId);
        });

        console.log(`Fetched ${accessibleWorkbooks.length} workbooks.`);

        // Displaying the filtered workbooks
        if (accessibleWorkbooks.length > 0) {
            accessibleWorkbooks.forEach((workbook, index) => {
                console.log(`#${index + 1}: Name: ${workbook.name}, URL: ${workbook.url}, Latest Version: ${workbook.latestVersion}`);
            });
        } else {
            console.log('No matching workbooks found for this member based on workbookIds.');
        }
    } catch (error) {
        console.error('Error listing accessible workbooks:', error);
    }
}

// Execute the function to list accessible workbooks
listAccessibleWorkbooks();