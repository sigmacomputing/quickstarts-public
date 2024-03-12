// Load and apply environment variables from the specified .env file.
require('dotenv').config({ path: 'rest-api-recipes/.env' });

// Import the function to obtain a bearer token from another script in the project.
const getBearerToken = require('./authenticate-bearer');

// Import the axios library for making HTTP requests.
const axios = require('axios');

// Define the base URL for the Sigma API.
const baseURL = 'https://aws-api.sigmacomputing.com/v2';

// Retrieve the Member ID from environment variables, which is to be used in the API request.
const memberId = process.env.MEMBERID;

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

  try {
    // Make a GET request to the specified URL, including the bearer token in the request headers for authentication.
    const response = await axios.get(recentsURL, {
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Accept': 'application/json'
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
