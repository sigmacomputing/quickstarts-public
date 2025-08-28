// Title: Create Workspace Permission
// Description: This script grants workspace permissions to either a member or team, with configurable permission levels (view, edit, admin).

// 1: Load environment variables from a specific .env file for configuration
require('dotenv').config({ path: 'recipes/.env' });

// 2" Import the function to obtain a bearer token from the authenticate-bearer module
const getBearerToken = require('../get-access-token');

// 3: Import Axios for making HTTP requests
const axios = require('axios');

// 4: Load use-case specific variables from environment variables
const baseURL = process.env.baseURL; // Your base URL
const memberId = process.env.MEMBERID; // Retrieve the memberId, from .env (optional - use either memberId or teamId)
const teamId = process.env.TEAMID; // Retrieve the teamId, from .env (optional - use either memberId or teamId)
const workspaceId = process.env.WORKSPACEID; // Retrieve the WorkspaceID from .env
// Map common permission names to valid Sigma workspace permissions
const rawPermission = process.env.PERMISSION || 'view';
const permissionMapping = {
    'view': 'view',
    'explore': 'explore', 
    'organize': 'organize',
    'edit': 'edit',
    'manage': 'edit',    // Map 'manage' to 'edit' (highest available)
    'admin': 'edit',     // Map 'admin' to 'edit' (highest available)
    'full': 'edit'       // Map 'full' to 'edit' (highest available)
};

const permission = permissionMapping[rawPermission.toLowerCase()] || 'view';

async function addNewWorkspacePermission() {
    // Validate the final permission value
    const validPermissions = ['view', 'explore', 'organize', 'edit'];
    if (!validPermissions.includes(permission)) {
        console.error(`Error: Invalid permission "${rawPermission}". Valid options: ${validPermissions.join(', ')}`);
        return;
    }
    
    // Log permission mapping if different
    if (rawPermission.toLowerCase() !== permission) {
        console.log(`Permission mapped: "${rawPermission}" → "${permission}"`);
    }
    const accessToken = await getBearerToken();
    if (!accessToken) {
        console.error('Failed to obtain Bearer token.');
        return;
    }

    const requestURL = `${baseURL}/workspaces/${workspaceId}/grants`;
    console.log(`URL sent to Sigma: ${requestURL}`);

    // Validate that either memberId or teamId is provided (but not both)
    if (!memberId && !teamId) {
        console.error('Error: Either MEMBERID or TEAMID must be provided in environment variables');
        return;
    }
    
    if (memberId && teamId) {
        console.error('Error: Cannot specify both MEMBERID and TEAMID. Choose one.');
        return;
    }

    // Build grantee object based on provided ID
    const grantee = memberId ? { memberId } : { teamId };
    const granteeType = memberId ? 'member' : 'team';
    const granteeId = memberId || teamId;
    
    console.log(`Granting ${permission} permission to ${granteeType}: ${granteeId}`);

    try {
        const response = await axios.post(requestURL, {
            grants: [{
                grantee,
                permission
            }]
        }, {
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${accessToken}`
            }
        });

        console.log('New workspace permission added successfully:', JSON.stringify(response.data, null, 2));
    } catch (error) {
        console.error('Error adding new workspace permission:', error.response ? error.response.data : error.message);
    }
}

if (require.main === module) {
    addNewWorkspacePermission();
}

module.exports = addNewWorkspacePermission;
