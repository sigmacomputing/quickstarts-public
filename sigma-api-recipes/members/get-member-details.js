// This script retrieves the member name for the specified memberID in .env

// This script retrieves the details of a specific member based on memberId

// 1: Load environment variables from a specific .env file for configuration
require('dotenv').config({ path: 'sigma-api-recipes/.env' });

// 2: Import the function to obtain a bearer token from the authenticate-bearer module
const getBearerToken = require('../get-access-token');

// 3: Import Axios for making HTTP requests
const axios = require('axios');

// 4: Load use-case specific variables from environment variables
const baseURL = process.env.baseURL; // Your base URL
const memberId = process.env.MEMBERID; // The specific memberId to find

// Define an asynchronous function to get member details.
async function getMemberDetails() {
  // Obtain a bearer token using the previously imported function.
  const accessToken = await getBearerToken();
  // If unable to obtain a token, log an error message and exit the function.
  if (!accessToken) {
    console.log('Failed to obtain Bearer token.');
    return;
  }

  try {
    // Construct the URL for accessing the API endpoint that retrieves member details.
    const memberURL = `${baseURL}/members/${memberId}`;

    // Make a GET request to the specified URL, including the bearer token in the request headers for authentication.
    const response = await axios.get(memberURL, {
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Accept': 'application/json'
      }
    });

    console.log(`URL sent to Sigma: ${memberURL}`); // Log the constructed URL before sending the request

    // Log the fetched member details to the console in a readable JSON format.
    const memberDetails = response.data;
    console.log("Member Details:", JSON.stringify(memberDetails, null, 2));

  } catch (error) {
    // If the request fails, log the error details.
    console.error('Error retrieving member details:', error.response ? error.response.data : error);
  }
}

// Execute the function to get member details.
getMemberDetails();