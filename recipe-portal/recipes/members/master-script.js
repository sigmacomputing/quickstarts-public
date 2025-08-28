// Title: Master Script  
// Description: Complete 5-step member onboarding workflow: 1) Create new member, 2) Create workspace, 3) Grant workspace permission, 4) Add to team, 5) Grant connection permission

// Parameters (only these should show in UI):
// - EMAIL: Base email for new member (unique email will be auto-generated)
// - NEW_MEMBER_FIRST_NAME: First name for new member
// - NEW_MEMBER_LAST_NAME: Last name for new member  
// - NEW_MEMBER_TYPE: Account type for new member (admin, build, view, analyze, act)
// - TEAMID: The team ID to add the new member to
// - CONNECTIONID: The connection ID to grant permissions for
// - WORKSPACE_NAME: Name for the new workspace (optional - defaults to "Workspace for {firstName}")
// - PERMISSION: Permission level for workspace (optional - defaults to 'view')
//
// Note: MEMBERID and WORKSPACEID are set automatically by this script - do not expose in UI

// Load environment variables from a specific .env file for configuration
require('dotenv').config({ path: 'recipes/.env' });

// Import necessary scripts for 5-step workflow
const createNewMember = require('./create-new');
const addNewWorkspace = require('./create-workspace');
const grantWorkspacePermission = require('./create-workspace-permission');
const addMemberToTeam = require('../teams/add-member-to-team');
const addNewConnectionPermission = require('./create-connection-permission');

// Define an asynchronous function to handle the onboarding process
async function onboardNewMember() {
    console.log('Starting the automated member onboarding workflow...');
    
    // Validate required environment variables
    const requiredVars = ['EMAIL', 'NEW_MEMBER_FIRST_NAME', 'NEW_MEMBER_LAST_NAME', 'NEW_MEMBER_TYPE', 'TEAMID', 'CONNECTIONID'];
    const missingVars = requiredVars.filter(varName => !process.env[varName]);
    
    if (missingVars.length > 0) {
        console.error('❌ Missing required environment variables:', missingVars.join(', '));
        return;
    }
    
    console.log('Environment Variables:');
    console.log('  Base Email:', process.env.EMAIL);
    console.log('  First Name:', process.env.NEW_MEMBER_FIRST_NAME);
    console.log('  Last Name:', process.env.NEW_MEMBER_LAST_NAME);
    console.log('  Account Type:', process.env.NEW_MEMBER_TYPE);
    console.log('  Team ID:', process.env.TEAMID);
    console.log('  Connection ID:', process.env.CONNECTIONID);
    console.log('  Workspace Name:', process.env.WORKSPACE_NAME || `Workspace for ${process.env.NEW_MEMBER_FIRST_NAME}`);
    console.log('  Permission Level:', process.env.PERMISSION || 'view');
    console.log('');

    try {
        // Step 1: Create new member
        console.log('=== STEP 1: Creating new member ===');
        const memberInfo = await createNewMember();
        if (!memberInfo || !memberInfo.memberId) {
            throw new Error('Failed to create new member');
        }
        console.log(`Step 1 complete: Member created with ID ${memberInfo.memberId}`);
        console.log('');

        // Set MEMBERID for subsequent scripts
        process.env.MEMBERID = memberInfo.memberId;
        
        // Clear require cache for modules that read environment variables at load time
        const memberScriptPaths = [
            require.resolve('./create-workspace-permission'),
            require.resolve('../teams/add-member-to-team'),
            require.resolve('./create-connection-permission')
        ];
        memberScriptPaths.forEach(scriptPath => {
            if (require.cache[scriptPath]) {
                delete require.cache[scriptPath];
            }
        });

        // Step 2: Create new workspace for the member
        console.log('=== STEP 2: Creating new workspace ===');
        const workspaceId = await addNewWorkspace();
        if (!workspaceId) {
            throw new Error('Failed to create workspace or get workspace ID');
        }
        console.log(`Step 2 complete: Workspace created with ID ${workspaceId}`);
        console.log('');

        // Step 3: Grant workspace permission to the new member
        console.log('=== STEP 3: Granting workspace permission ===');
        const originalWorkspaceId = process.env.WORKSPACEID;
        const originalTeamId = process.env.TEAMID;
        
        process.env.WORKSPACEID = workspaceId;
        // Temporarily unset TEAMID so the permission is granted to the member, not the team
        delete process.env.TEAMID;
        
        // Clear and re-require workspace permission module to pick up new WORKSPACEID and removed TEAMID
        const workspacePermissionPath = require.resolve('./create-workspace-permission');
        if (require.cache[workspacePermissionPath]) {
            delete require.cache[workspacePermissionPath];
        }
        const grantWorkspacePermissionFresh = require('./create-workspace-permission');
        await grantWorkspacePermissionFresh();
        
        // Restore original values
        if (originalWorkspaceId) {
            process.env.WORKSPACEID = originalWorkspaceId;
        } else {
            delete process.env.WORKSPACEID;
        }
        if (originalTeamId) {
            process.env.TEAMID = originalTeamId;
        }
        console.log('Step 3 complete: Workspace permissions granted');
        console.log('');

        // Step 4: Add member to team
        console.log('=== STEP 4: Adding member to team ===');
        // Clear and re-require team module to pick up fresh MEMBERID
        const teamPath = require.resolve('../teams/add-member-to-team');
        if (require.cache[teamPath]) {
            delete require.cache[teamPath];
        }
        const addMemberToTeamFresh = require('../teams/add-member-to-team');
        await addMemberToTeamFresh();
        console.log('Step 4 complete: Member added to team');
        console.log('');

        // Step 5: Grant connection permission to the member
        console.log('=== STEP 5: Granting connection permission ===');
        // Clear and re-require connection permission module to pick up fresh MEMBERID
        const connectionPath = require.resolve('./create-connection-permission');
        if (require.cache[connectionPath]) {
            delete require.cache[connectionPath];
        }
        const addNewConnectionPermissionFresh = require('./create-connection-permission');
        await addNewConnectionPermissionFresh();
        console.log('Step 5 complete: Connection permissions granted');
        console.log('');

        console.log('ONBOARDING COMPLETED SUCCESSFULLY');
        console.log(`New member ${memberInfo.email} (${memberInfo.memberId}) has been fully onboarded.`);
    } catch (error) {
        console.error('Onboarding failed:', error.message || error);
    }
}

// Execute the function to start the onboarding process
onboardNewMember();
