// Title: Generate Workbook Embed Path
// Description: This script generates secure embed URLs for Sigma workbooks using the official embed API.

// Load environment variables from a specific .env file for configuration
require('dotenv').config({ path: 'recipes/.env' });

// Import the function to obtain a bearer token from the authenticate-bearer module
const getBearerToken = require('./get-access-token');

// Import Axios for making HTTP requests
const axios = require('axios');

// Load use-case specific variables from environment variables
const baseURL = process.env.baseURL; // Base URL for the Sigma API
const workbookId = process.env.WORKBOOK_ID; // The workbook ID to generate embed URL for
const memberId = process.env.MEMBERID; // Member ID for user-specific embedding

// Generate embed URL for a specific workbook
async function generateEmbedURL(workbookId, memberId, accessToken) {
    const url = `${baseURL}/workbooks/${workbookId}/embeds`;
    console.log(`Generating embed URL for workbook: ${workbookId}`);
    
    try {
        const embedPayload = {
            embedType: "secure", // Options: "secure" | "public" | "application"
            sourceType: "workbook", // Options: "workbook" | "page" | "element"
            sourceId: workbookId, // The workbook ID to embed
            memberId: memberId, // Member ID for user-specific embedding
            // Add any additional embed options here as needed
        };

        const response = await axios.post(url, embedPayload, {
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                'Content-Type': 'application/json'
            }
        });

        console.log('Embed URL generated successfully:');
        console.log('Response:', JSON.stringify(response.data, null, 2));
        
        return response.data;
    } catch (error) {
        console.error(`Error generating embed URL: ${error}`);
        if (error.response) {
            console.error(`Response status: ${error.response.status}`);
            console.error(`Response headers: ${JSON.stringify(error.response.headers)}`);
            console.error(`Response body: ${JSON.stringify(error.response.data, null, 2)}`);
        } else {
            console.error(`Error details: ${error.message}`);
        }
        return null;
    }
}

// Main function to manage the overall workflow
async function main() {
    const accessToken = await getBearerToken();
    if (!accessToken) {
        console.error('Failed to obtain Bearer token.');
        return;
    }

    if (!workbookId) {
        console.error('WORKBOOK_ID is required to generate embed URL.');
        return;
    }

    if (!memberId) {
        console.error('MEMBERID is required for user-specific embedding.');
        return;
    }

    console.log(`Generating embed URL for workbook: ${workbookId}`);
    console.log(`Member ID: ${memberId}`);
    
    const embedResult = await generateEmbedURL(workbookId, memberId, accessToken);
    if (embedResult) {
        console.log('\n✅ Embed URL generation completed successfully!');
        if (embedResult.url) {
            console.log(`🔗 Embed URL: ${embedResult.url}`);
        }
    } else {
        console.error('❌ Failed to generate embed URL.');
    }
}

if (require.main === module) {
    main(); // Executes the main function if the file is run directly
}

module.exports = main; // Exports the main function to allow it to be used in other modules