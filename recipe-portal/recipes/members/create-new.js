// Title: Create New Member
// Description: This script creates a new member in Sigma after ensuring the email does not already exist.

// 1: Load environment variables from a specific .env file for configuration
require('dotenv').config({ path: 'recipes/.env' });

// 2: Import the function to obtain a bearer token from the authenticate-bearer module
const getBearerToken = require('../get-access-token');

// 3: Import Axios for making HTTP requests
const axios = require('axios');

// 4: Load use-case specific variables from environment variables
const baseURL = process.env.baseURL; // Your base URL
const baseEmail = process.env.EMAIL; // Retrieve the base email from environment variables

// Dynamically generate a unique email using the base email in the format: baseEmail+mmddhhmm@sigmacomputing.com
const now = new Date();
const timestamp = `${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}`;
const newMemberEmail = `${baseEmail.split('@')[0]}+${timestamp}@${baseEmail.split('@')[1]}`;
console.log(`Generated email for new member: ${newMemberEmail}`);

// Load additional member details from the environment variables
const newMemberFirstName = process.env.NEW_MEMBER_FIRST_NAME;
const newMemberLastName = process.env.NEW_MEMBER_LAST_NAME;
const newMemberType = process.env.NEW_MEMBER_TYPE;

async function memberExists(email, accessToken) {
    const requestURL = `${baseURL}/members?search=${encodeURIComponent(email)}`;
    console.log(`Checking if member exists with search parameter: ${email}`);
    try {
        const response = await axios.get(requestURL, {
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                'Accept': 'application/json',
            }
        });

        // Log the full response for debugging
        console.log('Response data:', JSON.stringify(response.data, null, 2));

        // Check if any member in the results matches the email exactly
        const members = response.data.entries || [];
        const exists = members.some(member => member.email.toLowerCase() === email.toLowerCase());

        console.log(`Member check result: ${exists ? 'Exists' : 'Does not exist'}`);
        return exists;
    } catch (error) {
        console.error('Error checking member existence:', error.response ? error.response.data : error.message);
        throw new Error('Failed to check member existence.');
    }
}

// Function to create a new member
async function addNewMember() {
    const accessToken = await getBearerToken();
    if (!accessToken) {
        console.error('Failed to obtain Bearer token.');
        return;
    }

    // Log the environment variables to validate inputs
    console.log(`New member details:
        Email: ${newMemberEmail}
        First Name: ${newMemberFirstName}
        Last Name: ${newMemberLastName}
        Member Type: ${newMemberType}`);

    // Check if the member already exists
    const exists = await memberExists(newMemberEmail, accessToken);
    if (exists) {
        console.log(`Member with email ${newMemberEmail} already exists. No action taken.`);
        return;
    }

    const requestURL = `${baseURL}/members`;
    console.log(`URL sent to Sigma: ${requestURL}`);

    try {
        // Make the API request to create the new member
        const response = await axios.post(requestURL, {
            email: newMemberEmail,
            firstName: newMemberFirstName,
            lastName: newMemberLastName,
            memberType: newMemberType, // Ensure this is passed correctly
        }, {
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${accessToken}`
            }
        });

        // Log the successful response
        const { memberId, memberType: createdMemberType } = response.data;
        console.log('New member added successfully:');
        console.log(`Member ID: ${memberId}`);
        console.log(`Account Type: ${createdMemberType}`);
        return { memberId, email: newMemberEmail, memberType: createdMemberType }; // Return member info for master script
    } catch (error) {
        // Handle errors and log details
        console.error('Error adding new member:', error.response ? error.response.data : error.message);
        return null;
    }
}

// Execute the function if this script is run directly
if (require.main === module) {
    addNewMember();
}

// Export the function for reuse
module.exports = addNewMember;