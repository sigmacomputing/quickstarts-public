// Title: Bulk Remove Team
// Description: This script bulk removes existing members from a team, based on the member's email, which is matched from the member-emails file.

// Load required modules and environment variables for script configuration.
require('dotenv').config({ path: 'recipes/.env' });
const getBearerToken = require('../get-access-token'); // Function to obtain an authentication token.
const axios = require('axios'); // HTTP client for making requests to Sigma's API.
const fs = require('fs'); // File system module to read the list of emails from a file.
const path = require('path'); // Module for handling file paths.

// Environment variables loaded from the .env file.
const baseURL = process.env.baseURL; // Base URL for Sigma's API endpoints.
const teamId = process.env.TEAMID; // Target team ID for assigning members.
const emailListPath = path.join(__dirname, '..', '.member-emails'); // Path to the file containing member emails.

// Function to find a member's ID by their email address.
async function findMemberIdByEmail(email, token) {
    const encodedEmail = encodeURIComponent(email); // Encode email to ensure it is URL-safe.
    const requestUrl = `${baseURL}/members?search=${encodedEmail}`; // Construct the request URL.
    console.log(`Searching for member by email with URL: ${requestUrl}`); // Log the request for debugging.
    try {
        const response = await axios.get(requestUrl, {
            headers: { Authorization: `Bearer ${token}` }, // Include the bearer token for authentication.
        });
        // Return the first matching member ID if found.
        const members = response.data.entries || [];
        const matchingMember = members.find(member => member.email.toLowerCase() === email.toLowerCase());
        return matchingMember ? matchingMember.memberId : null;
    } catch (error) {
        console.error(`Error searching for member by email (${email}):`, error);
        return null; // Return null if an error occurs or no member is found.
    }
}

// Function to add/remove a member to a specified team by their member ID.
      // change logging messages to remove instead of add
      async function addMemberToTeam(memberId, teamId, token) {
        const requestUrl = `${baseURL}/teams/${teamId}/members`; // API endpoint for adding a member to a team.
        
        //Change the job to remove a member:
        const payload = { add: [], remove: [memberId] }; // Payload specifying the member to add (and none to remove).
        const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }; // Request headers.
        
        // Log the request details for debugging.
    
        console.log(`Removed member to team with URL: ${requestUrl}`);
     //   console.log(`Headers:`, JSON.stringify(headers, null, 2));
        console.log(`Payload:`, JSON.stringify(payload, null, 2));
    
        try {
            const response = await axios.patch(requestUrl, payload, { headers });
            console.log(`Member ${memberId} removed from team ${teamId}. Response:`, response.data);
        } catch (error) {
            console.error(`Error removing member ${memberId} to team ${teamId}:`, error.response ? error.response.data : error);
        }
    }

// Main function to process member emails and assign them to the specified team.
async function processMembers(teamId, token) {
    const emails = fs.readFileSync(emailListPath, 'utf-8').split(','); // Read and split the list of emails.
    for (const email of emails) {
        const memberId = await findMemberIdByEmail(email.trim(), token); // Get member ID by email.
        if (memberId) {
            await addMemberToTeam(memberId, teamId, token); // Add the member to the team.
        } else {
            console.log(`Member not found for email: ${email}`); // Log if no member ID is found for an email.
        }
    }
}

// Entry point of the script.
async function main() {
    const token = await getBearerToken(); // Fetch the bearer token.
    if (!token) {
        console.error('Failed to obtain bearer token.');
        return;
    }
    await processMembers(teamId, token); // Process member assignments.
}

main().catch(console.error); // Execute the main function and catch any errors.
