// This script can be used to on-board new members in Sigma and set common items like 

// 1: Load environment variables from a specific .env file for configuration
require('dotenv').config({ path: 'rest-api-recipes/.env' });

// 2: Import the function to obtain a bearer token from the authenticate-bearer module
const getBearerToken = require('../get-access-token');

// 3: Import Axios for making HTTP requests
const axios = require('axios');

// 4: Load use-case specific variables from environment variables
const baseURL = process.env.baseURL; // Your base URL
const baseEmail = process.env.EMAIL; // Retrieve the base email from environment variables

// Dynamically generate a unique email using the base email
// We do this to ensure that we are always creating a new member when testing. Be sure to delete these users later if you prefer.
const newMemberEmail = `${baseEmail.split('@')[0]}+${new Date().getTime()}@${baseEmail.split('@')[1]}`;

const newMemberFirstName = process.env.NEW_MEMBER_FIRST_NAME; // New member's first name
const newMemberLastName = process.env.NEW_MEMBER_LAST_NAME; // New member's last name
const newMemberType = process.env.NEW_MEMBER_TYPE; // New member's type 

async function addNewMember() {
    const accessToken = await getBearerToken();
    if (!accessToken) {
        console.error('Failed to obtain Bearer token.');
        return;
    }

    const requestURL = `${baseURL}/members`;
    console.log(`URL sent to Sigma: ${requestURL}`);

    try {
        const response = await axios.post(requestURL, {
            email: newMemberEmail,
            firstName: newMemberFirstName,
            lastName: newMemberLastName,
            memberType: newMemberType,
        }, {
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${accessToken}`
            }
        });

        console.log('New member added successfully:', JSON.stringify(response.data, null, 2));
    } catch (error) {
        console.error('Error adding new member:', error.response ? error.response.data : error.message);
    }
}

if (require.main === module) {
    addNewMember();
}

module.exports = addNewMember;
