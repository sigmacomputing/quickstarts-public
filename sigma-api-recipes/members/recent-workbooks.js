// This script returns all the workbooks for a specified member, ordered by most recent

// 1: Load environment variables from a specific .env file for configuration
require('dotenv').config({ path: 'sigma-api-recipes/.env' });

// 2: Import the function to obtain a bearer token from the authenticate-bearer module
const getBearerToken = require('../get-access-token');

// 3: Import Axios for making HTTP requests
const axios = require('axios');

// 4: Load use-case specific variables from environment variables
const memberId = process.env.MEMBERID; // The unique identifier of the member whose type you want to update
const baseURL = process.env.baseURL; // Your base URL

// Define an asynchronous function to list recent documents and folders accessible to a specific member.
async function listRecentDocuments() {
  // Obtain a bearer token using the previously imported function.
  const accessToken = await getBearerToken();
  // If unable to obtain a token, log an error message and exit the function.
  if (!accessToken) {
    console.log('Failed to obtain Bearer token.');
    return;
  }

  // Construct the URL for accessing the API endpoint that lists recent documents and folders.
  const recentsURL = `${baseURL}/members/${memberId}/files/recents`;

  console.log(`URL sent to Sigma: ${recentsURL}`); // Log the constructed URL before sending the request

  try {
    // Make a GET request to the specified URL, including the bearer token in the request headers for authentication.
    const response = await axios.get(recentsURL, {
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Accept': 'application/json' // Specify the accepted response format
      }
    });

    // Extract the entries array from the response data, which contains the documents and folders.
    const entries = response.data.entries;

    // Process each entry to extract and keep only the name, permission, and lastInteractionAt fields.
    // Then, sort the processed entries by the lastInteractionAt field in descending order.
    const processedEntries = entries.map(({ name, permission, lastInteractionAt }) => ({
      name,
      permission,
      lastInteractionAt
    })).sort((a, b) => new Date(b.lastInteractionAt) - new Date(a.lastInteractionAt));

    // Log the processed and sorted entries to the console in a readable JSON format.
    console.log("Recent documents and folders:", JSON.stringify(processedEntries, null, 2));
  } catch (error) {
    // If the request fails, log the error details.
    console.error('Error listing recent documents:', error.response ? error.response.data : error);
  }
}

// Execute the function to list recent documents and folders.
listRecentDocuments();