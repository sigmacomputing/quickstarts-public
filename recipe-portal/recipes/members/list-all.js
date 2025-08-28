// Title: List All Members
// Description: This script lists all members in the organization with pagination support.
//
// PREREQUISITES:
// - Valid authentication credentials with admin/member management permissions
// - Organization must have member data to retrieve
// - For large organizations: Results are paginated, use LIMIT and MAX_PAGES parameters to control output

// Load environment variables from a specific .env file for configuration
require('dotenv').config({ path: 'recipes/.env' });

// Import the function to obtain a bearer token from the authenticate-bearer module
const getBearerToken = require('../get-access-token');

// Import Axios for making HTTP requests
const axios = require('axios');
const fs = require('fs'); // Import File System for saving output

// Load use-case specific variables from environment variables
const baseURL = process.env.baseURL; // Your base URL
const limit = parseInt(process.env.LIMIT) || 100000; // Maximum members to retrieve (Default: 100,000 | Max: 1,000,000)
const maxPages = parseInt(process.env.MAX_PAGES) || 0; // Maximum pages to fetch (0 = all pages)
const maxLimit = 1000000;

async function listMembers() {
    try {
        // Validate row limit  
        let actualLimit = limit;
        if (limit > maxLimit) {
            actualLimit = maxLimit;
        }
        
        console.log('Authenticating...');
        let token = await getBearerToken();
        if (!token) {
            console.log('ERROR: Authentication failed');
            return;
        }
        console.log('Authentication successful');

        console.log('Fetching members (limit: ' + actualLimit + ')...');
        
        let hasMore = true;
        let nextPage = null;
        let currentPage = 0;
        let allMembers = [];

        while (hasMore && (maxPages === 0 || currentPage < maxPages)) {
            try {
                currentPage++;
                
                // Use 1000 per page (API max) for efficiency, but respect overall actualLimit
                const perPageLimit = Math.min(1000, actualLimit - allMembers.length);
                let url = baseURL + '/members?limit=' + perPageLimit;
                if (nextPage) {
                    url += '&page=' + nextPage;
                }
                
                console.log('Fetching page ' + currentPage + '...');

                const response = await axios.get(url, {
                    headers: { Authorization: 'Bearer ' + token }
                });

            // Process current page members
            const entries = response.data.entries || [];
            console.log('Found ' + entries.length + ' members on page ' + currentPage);

            // Collect all members for JSON output
            allMembers = allMembers.concat(entries);

            // Check if we've reached the specified limit
            if (allMembers.length >= actualLimit) {
                console.log('Reached specified limit of ' + actualLimit + ' members');
                allMembers = allMembers.slice(0, actualLimit);
                hasMore = false;
                break;
            }

            // Handle different possible response structures for pagination
            const apiHasMore = response.data.hasMore;
            const apiNextPage = response.data.nextPage;
            
            // If hasMore is undefined but nextPage exists, assume there are more pages
            // If hasMore is explicitly false, respect that
            if (apiHasMore === false) {
                hasMore = false;
            } else if (apiNextPage) {
                hasMore = true;
            } else {
                hasMore = false;
            }
            
            nextPage = apiNextPage;

            } catch (error) {
                console.log('Error fetching members: ' + error.message);
                break;
            }
        }

        console.log('\\n=== MEMBER DETAILS ===');
        console.log('Found ' + allMembers.length + ' members total:');
        console.log('');
        
        // Display detailed information for each member in a clean format
        allMembers.forEach((member, index) => {
            console.log('=== Member #' + (index + 1) + ' ===');
            console.log('Name: ' + ((member.firstName + ' ' + member.lastName).trim() || 'Unknown'));
            console.log('Email: ' + (member.email || 'No email'));
            console.log('Type: ' + (member.memberType || 'N/A'));
            console.log('Member ID: ' + (member.memberId || 'Unknown'));
            console.log('Created: ' + (member.createdAt ? new Date(member.createdAt).toLocaleDateString() : 'Unknown'));
            console.log('Updated: ' + (member.updatedAt ? new Date(member.updatedAt).toLocaleDateString() : 'Unknown'));
            console.log('');
        });
        
        console.log('=== SUMMARY ===');
        console.log('Total Members: ' + allMembers.length);
        console.log('Export completed successfully');
        
        // Brief delay before exit to allow UI to process the completion
        setTimeout(() => {
            process.exit(0);
        }, 1000);

    } catch (error) {
        console.log('FATAL ERROR: ' + error.message);
    }
}

// Execute the function to list members.
listMembers();
