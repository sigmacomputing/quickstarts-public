// This script grants workspace permission to a team and changes the tag value
// Swagger: https://help.sigmacomputing.com/reference/listversiontag-1

// 1: Load environment variables from a specific .env file for configuration
require('dotenv').config({ path: 'rest-api-recipes/.env' });

// 2: Import the function to obtain a bearer token from the authenticate-bearer module
const getBearerToken = require('../get-access-token');

// 3: Import Axios for making HTTP requests
const axios = require('axios');

// 4: Load use-case specific variables from environment variables
const baseURL = process.env.baseURL; // Your base URL
const memberId = process.env.MEMBERID; // The unique identifier of the member whose type you want to update
const teamId = process.env.TEAMID; // Team ID for granting permission
const workspaceId = process.env.WORKSPACEID; // Workspace ID for granting permission
const tagName = process.env.TAGNAME; // Existing tag name
const tagValue = process.env.TAGVALUE; // New tag value
const fileName = process.env.FILENAME; // File name for inodeId retrieval
const filePath = process.env.FILEPATH; // File path for inodeId retrieval

// Function to retrieve the tagId based on the tag name
async function getTagId(accessToken) {
    try {
        const listTagsURL = `${baseURL}/tags?search=${tagName}`;
        console.log(`URL sent to Sigma: ${listTagsURL}`);

        const response = await axios.get(listTagsURL, {
            headers: {
                'Authorization': `Bearer ${accessToken}`
            }
        });

        const tagData = response.data.entries[0];
        if (!tagData) {
            console.error('Tag not found:', tagName);
            return null;
        }

        const tagId = tagData.versionTagId;
        console.log('TagId:', tagId);
        return tagId;
    } catch (error) {
        console.error('Error fetching tagId:', error.response ? error.response.data : error);
        return null;
    }
}

// Function to grant workspace permission to a team
async function grantWorkspacePermission(tagId, accessToken, inodeId) {
    try {
        // Construct the URL for the grants endpoint
        const grantsURL = `${baseURL}/grants`;

        // Define the payload for granting workspace permission to a team
        const grantPayload = {
            grantee: {
                teamId : teamId
            },
            permission: "edit",
            workspaceId: workspaceId,
            versionTagId: tagId,
            inodeId: inodeId
        };

        // Make a POST request to the grants endpoint with the payload
        const response = await axios.post(grantsURL, grantPayload, {
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                'Content-Type': 'application/json'
            }
        });

        console.log('Workspace permission granted successfully:', response.data);
    } catch (error) {
        console.error('Error granting workspace permission:', error.response ? error.response.data : error);
    }
}

// Function to retrieve the inodeId for the specified file
async function getInodeId(accessToken) {
    try {
        // Construct the URL for retrieving the inodeId
        const filesURL = `${baseURL}/files`;

        // Define the query parameters for searching the file by name and path
        const queryParams = {
            name: fileName,
            path: filePath
        };

        // Make a GET request to the files endpoint with the query parameters
        const response = await axios.get(filesURL, {
            params: queryParams,
            headers: {
                'Authorization': `Bearer ${accessToken}`
            }
        });

        const fileData = response.data.entries[0];
        if (!fileData) {
            console.error('File not found:', fileName);
            return null;
        }

        const inodeId = fileData.urlId;
        console.log('InodeId:', inodeId);
        return inodeId;

    } catch (error) {
        console.error('Error fetching inodeId:', error.response ? error.response.data : error);
        return null;
    }
}

// Execute the script
async function executeScript() {
    try {
        const accessToken = await getBearerToken();
        if (!accessToken) {
            console.error('Failed to obtain Bearer token.');
            return;
        }

        const tagId = await getTagId(accessToken);
        if (!tagId) {
            console.error('Failed to retrieve tagId. Cannot proceed.');
            return;
        }

        const inodeId = await getInodeId(accessToken); // Obtain inodeId
        if (!inodeId) {
            console.error('Failed to retrieve inodeId. Cannot proceed.');
            return;
        }

        await grantWorkspacePermission(tagId, accessToken, inodeId); // Pass inodeId to grantWorkspacePermission

    } catch (error) {
        console.error('Error executing script:', error.response ? error.response.data : error);
    }
}

// Call the function to execute the script
executeScript();
