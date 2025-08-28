// Title: Copy Workbook Folder
// Description: This script copies a workbook folder from one location to another.

// Load environment variables from a specific .env file for configuration
require('dotenv').config({ path: 'recipes/.env' });

// Import the function to obtain a bearer token from the authenticate-bearer module
const getBearerToken = require('./get-access-token');

// Import Axios for making HTTP requests
const axios = require('axios');

// Load use-case specific variables from environment variables
const baseURL = process.env.baseURL; // Base URL for the Sigma API
const workbookId = process.env.WORKBOOK_ID; // Workbook ID to copy
const memberId = process.env.MEMBERID; // ID of the member whose "My Documents" folder we'll use
const newWorkbookName = process.env.NEW_WORKBOOK_NAME || 'Copy of Workbook'; // Name for the copied workbook
const newWorkbookDescription = process.env.NEW_WORKBOOK_DESCRIPTION || 'Copied workbook'; // Description for the copied workbook

// Function to retrieve the ID of the member's "My Documents" folder
async function getMyDocumentsFolderId(accessToken) {
    try {
        // Send the request to retrieve the member's details
        const response = await axios.get(
            `${baseURL}/members/${memberId}`,
            { headers: { Authorization: `Bearer ${accessToken}` } }
        );

        // Extract the ID of the member's "My Documents" folder
        const homeFolderId = response.data.homeFolderId;

        // Log the retrieved folder ID
        console.log('Retrieved "My Documents" folder ID:', homeFolderId);

        return homeFolderId;
    } catch (error) {
        // Log any errors that occur during the process
        console.error('Failed to retrieve "My Documents" folder ID:', error.response ? error.response.data : error);
        return null;
    }
}

// Function to copy the workbook to the specified folder
async function copyWorkbook(accessToken, destinationFolderId) {
    try {
        // Define the request payload to copy the workbook
        const copyPayload = {
            name: newWorkbookName, // Name from environment variable or default
            description: newWorkbookDescription, // Description from environment variable or default
            ownerId: memberId, // Specify the ID of the user who will own the copied workbook
            destinationFolderId: destinationFolderId // Use the passed destinationFolderId argument
        };

        console.log(`Copying workbook to: "${newWorkbookName}"`);

        // Send the request to copy the workbook
        const response = await axios.post(
            `${baseURL}/workbooks/${workbookId}/copy`,
            copyPayload,
            { headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' } }
        );

        // Log the success message and copied workbook details
        console.log('Workbook copy initiated successfully.');
        console.log('Copied workbook details:', response.data);

        // Return the ID of the copied workbook for further processing if needed
        return response.data.workbookId;
    } catch (error) {
        // Log any errors that occur during the process
        console.error('Failed to copy workbook:', error.response ? error.response.data : error);
        return null;
    }
}

// Main function to execute the workflow
async function main() {
    // Obtain the bearer token for authentication
    const accessToken = await getBearerToken();
    if (!accessToken) {
        console.error('Failed to obtain bearer token.');
        return;
    }

    // Retrieve the ID of the member's "My Documents" folder
    const myDocumentsFolderId = await getMyDocumentsFolderId(accessToken);
    if (!myDocumentsFolderId) {
        console.error('Failed to retrieve "My Documents" folder ID.');
        return;
    }

    // Copy the workbook and place it in the "My Documents" folder
    const copiedWorkbookId = await copyWorkbook(accessToken, myDocumentsFolderId); // Pass myDocumentsFolderId here
    if (!copiedWorkbookId) {
        console.error('Failed to copy workbook.');
        return;
    }

    // Perform any additional actions with the copied workbook if needed
    console.log(`Workbook successfully copied with ID: ${copiedWorkbookId}`);
}

// Execute the main function
main();