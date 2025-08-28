// Title: Create Workspace
// Description: This script creates a new workspace, named using the memberId from .env.

// 1: Load environment variables from a specific .env file for configuration
require('dotenv').config({ path: 'recipes/.env' });

// 2" Import the function to obtain a bearer token from the authenticate-bearer module
const getBearerToken = require('../get-access-token');

// 3: Import Axios for making HTTP requests
const axios = require('axios');

// 4: Load use-case specific variables from environment variables
const baseURL = process.env.baseURL; // Your base URL
const memberId = process.env.MEMBERID; // Retrieve the memberId to create a workspace for
const workspaceName = process.env.WORKSPACE_NAME || `Workspace for Member ${process.env.MEMBERID}`; // Custom name or default
const noDuplicates = process.env.NO_DUPLICATES !== 'false'; // Default to true unless explicitly set to false

async function addNewWorkspace() {
    const accessToken = await getBearerToken();
    if (!accessToken) {
        console.error('Failed to obtain Bearer token.');
        return;
    }

    const requestURL = `${baseURL}/workspaces`;
    console.log(`URL sent to Sigma: ${requestURL}`);
    console.log(`Creating workspace: "${workspaceName}" with noDuplicates: ${noDuplicates}`);

    try {
        const response = await axios.post(requestURL, {
            name: workspaceName,
            noDuplicates: noDuplicates
        }, {
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${accessToken}`
            }
        });

        // Handle both new workspace creation and existing workspace (duplicate prevention)
        let workspaceId = null;
        let isNewWorkspace = false;
        
        if (response.data && response.data.workspaceId) {
            // New workspace created
            workspaceId = response.data.workspaceId;
            isNewWorkspace = true;
        } else if (response.data && response.data.workspaceIds && response.data.workspaceIds.length > 0) {
            // Existing workspace found (duplicate prevention)
            workspaceId = response.data.workspaceIds[0];
            isNewWorkspace = false;
        }
        
        if (workspaceId) {
            if (isNewWorkspace) {
                console.log('New workspace created successfully:');
            } else {
                console.log('Workspace found (duplicate name prevented, using existing):');
            }
            console.log(`   Workspace ID: ${workspaceId}`);
            console.log(`   Workspace Name: "${response.data.name || workspaceName}"`);
            if (response.data.url) {
                console.log(`   URL: ${response.data.url}`);
            }
            if (response.data.path) {
                console.log(`   Path: ${response.data.path}`);
            }
            // Show all available fields for reference
            console.log('   All returned fields:', Object.keys(response.data));
            if (Object.keys(response.data).length <= 5) {
                console.log('   Full response:', JSON.stringify(response.data, null, 2));
            }
            return workspaceId; // Return workspace ID for master script
        } else {
            console.log('Workspace creation failed - unexpected response format:');
            console.log('   Full response:', JSON.stringify(response.data, null, 2));
            return null;
        }
    } catch (error) {
        if (error.response) {
            const errorData = error.response.data;
            if (errorData.code === 'conflict' || errorData.message?.includes('duplicate') || errorData.message?.includes('already exists')) {
                console.log('Workspace creation failed - duplicate name:');
                console.log(`   A workspace named "${workspaceName}" already exists.`);
                console.log('   Set NO_DUPLICATES=false to allow duplicates, or choose a different WORKSPACE_NAME.');
            } else {
                console.error('Error creating workspace:', errorData);
            }
        } else {
            console.error('Network error creating workspace:', error.message);
        }
    }
}

if (require.main === module) {
    addNewWorkspace();
}

module.exports = addNewWorkspace;
