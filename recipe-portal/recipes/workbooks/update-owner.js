// Title: Update Owner
// Description: This script updates the ownership of a specified inode in Sigma using the "Update an inode" endpoint.

// Load environment variables from a specific .env file for configuration
require('dotenv').config({ path: 'recipes/.env' });

// Import the function to obtain a bearer token from the authenticate-bearer module
const getBearerToken = require('../get-access-token');

// Import Axios for making HTTP requests
const axios = require('axios');

// Load use-case specific variables from environment variables
const baseURL = process.env.baseURL; // Base URL for the Sigma API
const memberid = process.env.MEMBERID; // New member ID to assign to the inode as owner
const workbookId = process.env.WORKBOOK_ID; // Workbook ID to be used as the urlId for the inode

// Function to update the ownerId of a specified inode using the workbookId
async function updateInodeOwner(workbookId) {
    const token = await getBearerToken();
    if (!token) {
        console.error('Failed to obtain Bearer token.');
        return;
    }

    try {
        const response = await axios.patch(
            `${baseURL}/files/${workbookId}`,
            { ownerId: memberid }, // Use `ownerId` with `memberid` value from .env
            {
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                }
            }
        );
        console.log('Inode updated successfully:', response.data);
    } catch (error) {
        console.error('Error updating inode:', error.response ? error.response.data : error);
    }
}

// Execute the update function
updateInodeOwner(workbookId);
