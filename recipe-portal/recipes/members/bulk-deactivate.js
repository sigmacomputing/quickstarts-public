// Title: Bulk Deactivate
// Description: This script identifies users in Sigma matching a specified name pattern, retrieves their status, and deactivates (soft-deletes) them.

// Load environment variables from a specific .env file for configuration
require('dotenv').config({ path: 'recipes/.env' });

// Import the function to obtain a bearer token from the authenticate-bearer module
const getBearerToken = require('../get-access-token');

// Import Axios for making HTTP requests
const axios = require('axios');

// Load use-case specific variables from environment variables
const baseURL = process.env.baseURL; // Base URL for the Sigma API
const userNamePattern = new RegExp(process.env.USER_NAME_PATTERN, 'i'); // Regex pattern for user names (case-insensitive)
const dryRun = process.env.DRY_RUN === 'true'; // Boolean flag for dry run mode (preview without actual deactivation)

// Function to fetch the isInactive status of a user by memberId
async function fetchIsInactiveStatus(memberId, accessToken) {
    const url = `${baseURL}/members/${memberId}`; // API endpoint to get member details
    console.log(`Fetching isInactive status for memberId: ${memberId} at URL: ${url}`);
    try {
        const response = await axios.get(url, {
            headers: {
                Authorization: `Bearer ${accessToken}`,
            },
        });
        return response.data.isInactive || false; // Return isInactive status or false if not set
    } catch (error) {
        console.error(`Error fetching isInactive status for memberId: ${memberId}`, error.response ? error.response.data : error);
        return false; // Default to false if an error occurs
    }
}

// Function to list all members and filter by name using the regex pattern
async function listUsers(accessToken) {
    const url = `${baseURL}/members?includeInactive=true`; // Include inactive users in the list
    console.log(`Listing users from: ${url}`);
    try {
        const response = await axios.get(url, {
            headers: {
                Authorization: `Bearer ${accessToken}`,
            },
        });

        // Filter users by name (firstName + lastName) using regex pattern
        const filteredUsers = response.data.entries.filter(user =>
            userNamePattern.test(`${user.firstName} ${user.lastName}`)
        );

        // Fetch isInactive status for each filtered user
        const usersWithStatus = [];
        for (const user of filteredUsers) {
            const isInactive = await fetchIsInactiveStatus(user.memberId, accessToken);
            if (!isInactive) {
                usersWithStatus.push({ ...user, isInactive });
            }
        }

        console.log('Filtered Users with isInactive Status:', usersWithStatus);
        return usersWithStatus;
    } catch (error) {
        console.error(`Error fetching users: ${error}`);
        return [];
    }
}

// Function to "soft-delete" (deactivate) a member
async function deleteUser(user, accessToken) {
    try {
        const url = `${baseURL}/members/${user.memberId}`;
        const response = await axios.delete(url, {
            headers: {
                Authorization: `Bearer ${accessToken}`,
                Accept: 'application/json',
            },
        });
        console.log(`Deactivated (deleted) user: ${user.firstName} ${user.lastName} (ID: ${user.memberId})`);
        console.log('Response:', response.data);
    } catch (error) {
        console.error(`Error deactivating (deleting) user ${user.firstName} ${user.lastName}:`, error.response ? error.response.data : error);
    }
}

// Main function to manage the overall workflow
async function main() {
    const accessToken = await getBearerToken();
    if (!accessToken) {
        console.error('Failed to obtain Bearer token.');
        return;
    }

    const users = await listUsers(accessToken);
    if (users.length > 0) {
        console.log(`Found ${users.length} active user(s) matching the pattern.`);
        
        if (dryRun) {
            console.log('🔍 DRY RUN MODE: Preview of users that would be deactivated:');
            for (const user of users) {
                console.log(`- Would deactivate: ${user.firstName} ${user.lastName} (${user.email}) [ID: ${user.memberId}]`);
            }
            console.log('No actual changes made. Set DRY_RUN=false to perform actual deactivation.');
        } else {
            console.log('🚀 LIVE MODE: Deactivating matched users...');
            for (const user of users) {
                await deleteUser(user, accessToken); // Actually deactivate the user
            }
        }
    } else {
        console.log('No active users matched the specified pattern.');
    }
}

// Execute the main function
main();
