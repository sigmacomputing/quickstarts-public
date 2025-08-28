// Title: Bulk Create Members
// Description: This script creates multiple new members in Sigma from a list of emails, with configurable member type and duplicate checking.

// 1: Load environment variables from a specific .env file for configuration
require('dotenv').config({ path: 'recipes/.env' });

// 2: Import the function to obtain a bearer token from the authenticate-bearer module
const getBearerToken = require('../get-access-token');

// 3: Import Axios for making HTTP requests
const axios = require('axios');
const fs = require('fs');
const path = require('path');

// 4: Load use-case specific variables from environment variables
const baseURL = process.env.baseURL; // Your base URL
const defaultMemberType = process.env.NEW_MEMBER_TYPE || 'view'; // Default member type for all created members
const emailListPath = path.join(__dirname, '..', '.member-emails'); // Path to the file containing member emails

// Function to check if a member already exists
async function memberExists(email, accessToken) {
    const requestURL = `${baseURL}/members?search=${encodeURIComponent(email)}`;
    try {
        const response = await axios.get(requestURL, {
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                'Accept': 'application/json',
            }
        });

        // Check if any member in the results matches the email exactly
        const members = response.data.entries || [];
        const exists = members.some(member => member.email.toLowerCase() === email.toLowerCase());
        return exists;
    } catch (error) {
        console.error(`Error checking if member exists (${email}):`, error.response ? error.response.data : error.message);
        return false; // Assume doesn't exist if we can't check
    }
}

// Function to create a single member
async function createMember(email, memberType, accessToken) {
    // Extract first and last name from email (fallback approach)
    const emailUsername = email.split('@')[0];
    const nameParts = emailUsername.split(/[._-]/);
    const firstName = nameParts[0] || 'User';
    const lastName = nameParts[1] || 'Name';

    const requestURL = `${baseURL}/members`;
    
    try {
        const response = await axios.post(requestURL, {
            email: email,
            firstName: firstName.charAt(0).toUpperCase() + firstName.slice(1), // Capitalize first letter
            lastName: lastName.charAt(0).toUpperCase() + lastName.slice(1),   // Capitalize first letter
            memberType: memberType
        }, {
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${accessToken}`
            }
        });

        return {
            success: true,
            memberId: response.data.memberId,
            email: email,
            memberType: response.data.memberType
        };
    } catch (error) {
        return {
            success: false,
            email: email,
            error: error.response ? error.response.data : error.message
        };
    }
}

// Main function to process bulk member creation
async function bulkCreateMembers() {
    console.log('Starting bulk member creation process...');
    
    // Get access token
    const accessToken = await getBearerToken();
    if (!accessToken) {
        console.error('Failed to obtain Bearer token.');
        return;
    }

    // Check if email file exists
    if (!fs.existsSync(emailListPath)) {
        console.error(`Email list file not found: ${emailListPath}`);
        console.error('Please create a .member-emails file in the recipes directory with comma-separated email addresses.');
        return;
    }

    // Read and parse email list
    let emails;
    try {
        const emailContent = fs.readFileSync(emailListPath, 'utf-8');
        emails = emailContent.split(',').map(email => email.trim()).filter(email => email.length > 0);
    } catch (error) {
        console.error('Error reading email list file:', error.message);
        return;
    }

    if (emails.length === 0) {
        console.error('No emails found in the email list file.');
        return;
    }

    console.log(`Found ${emails.length} email(s) to process:`);
    console.log(`Default member type: ${defaultMemberType}`);
    console.log('');

    // Process each email
    const results = {
        created: [],
        skipped: [],
        failed: []
    };

    for (let i = 0; i < emails.length; i++) {
        const email = emails[i];
        console.log(`Processing ${i + 1}/${emails.length}: ${email}`);

        // Check if member already exists
        const exists = await memberExists(email, accessToken);
        if (exists) {
            console.log(`  Skipped: Member already exists`);
            results.skipped.push({ email, reason: 'Already exists' });
            continue;
        }

        // Create the member
        const result = await createMember(email, defaultMemberType, accessToken);
        if (result.success) {
            console.log(`  Created: Member ID ${result.memberId}`);
            results.created.push(result);
        } else {
            console.log(`  Failed: ${typeof result.error === 'object' ? JSON.stringify(result.error) : result.error}`);
            results.failed.push(result);
        }

        // Small delay to avoid rate limiting
        await new Promise(resolve => setTimeout(resolve, 500));
    }

    // Print summary
    console.log('');
    console.log('=== BULK MEMBER CREATION SUMMARY ===');
    console.log(`Total processed: ${emails.length}`);
    console.log(`Successfully created: ${results.created.length}`);
    console.log(`Skipped (already exist): ${results.skipped.length}`);
    console.log(`Failed: ${results.failed.length}`);
    
    if (results.created.length > 0) {
        console.log('');
        console.log('Created members:');
        results.created.forEach(member => {
            console.log(`  ${member.email} → ${member.memberId} (${member.memberType})`);
        });
    }

    if (results.failed.length > 0) {
        console.log('');
        console.log('Failed members:');
        results.failed.forEach(failure => {
            console.log(`  ${failure.email} → Error: ${typeof failure.error === 'object' ? JSON.stringify(failure.error) : failure.error}`);
        });
    }

    console.log('');
    console.log('Bulk member creation completed.');
}

// Execute the function if this script is run directly
if (require.main === module) {
    bulkCreateMembers();
}

// Export the function for reuse
module.exports = bulkCreateMembers;