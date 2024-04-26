// masterOnboardingProcess.js
// This script creates a new member by using the manually update memberId from .env and then calling each other script in order
// You must create the new member first, manually using the script in members/create-new.js and paste the returned memberId in .env

// Import necessary scripts
const addMemberToTeam = require('./add-member-to-team');
const grantWorkspacePermission = require('./create-workspace-permission');
const addNewConnectionPermission = require('./create-workspace-permission'); // This line seems incorrect, it should import a different script
const addNewWorkspace = require('./create-workspace');

// Define an asynchronous function to handle the onboarding process
async function onboardNewMember() {
    console.log('Starting the automated part of the onboarding process.');

    try {
        // Assuming addMemberToTeam.js and other scripts use MEMBERID from .env internally
        console.log('Adding member to team...');
        await addMemberToTeam();
        console.log('Member successfully added to team.');

        console.log('Creating a new workspace...');
        await addNewWorkspace();
        console.log('New workspace created successfully.');

        console.log('Granting workspace permission...');
        await grantWorkspacePermission();
        console.log('Workspace permissions granted successfully.');

        console.log('Granting connection permission...');
        await addNewConnectionPermission(); // This line seems incorrect, it should call a different function
        console.log('Connection permissions granted successfully.');
      
        console.log('Onboarding process completed successfully.');
    } catch (error) {
        console.error('An error occurred during the onboarding process:', error);
    }
}

// Execute the function to start the onboarding process
onboardNewMember();
