// This script returns all members

// 1: Load environment variables from a specific .env file for configuration
require('dotenv').config({ path: 'sigma-api-recipes/.env' });

// 2: Import the function to obtain a bearer token from the authenticate-bearer module
const getBearerToken = require('../get-access-token');

// 3: Import Axios for making HTTP requests
const axios = require('axios');

// 4: Load use-case specific variables from environment variables
const baseURL = process.env.baseURL; // Your base URL

// Define an asynchronous function to list members.
async function listMembers() {
  // Obtain a bearer token using the previously imported function.
  const accessToken = await getBearerToken();
  // If unable to obtain a token, log an error message and exit the function.
  if (!accessToken) {
    console.log('Failed to obtain Bearer token.');
    return;
  }

  // Initialize an empty array to store all members
  let allMembers = [];

  // Initialize pagination variables
  let page = 1;
  let nextPage = true;

  try {
    // Make requests until there are no more pages to fetch
    while (nextPage) {
      // Construct the URL for accessing the API endpoint that lists members for the current page.
      const membersURL = `${baseURL}/members?page=${page}`;

      // Make a GET request to the specified URL, including the bearer token in the request headers for authentication.
      const response = await axios.get(membersURL, {
        headers: {
          'Authorization': `Bearer ${accessToken}`,
          'Accept': 'application/json'
        }
      });

      console.log(`URL sent to Sigma: ${membersURL}`); // Log the constructed URL before sending the request

      // Assuming the response contains an array of members directly
      const members = response.data;

      // Concatenate the fetched members to the array of all members
      allMembers = allMembers.concat(members);

      // Update pagination variables for the next iteration
      nextPage = response.data.nextPage;
      page++;
    }

    // Log all the fetched members to the console in a readable JSON format.
    console.log("Members:", JSON.stringify(allMembers, null, 2));
  } catch (error) {
    // If the request fails, log the error details.
    console.error('Error listing members:', error.response ? error.response.data : error);
  }
}

// Execute the function to list members.
listMembers();