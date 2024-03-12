// Load environment variables from a specific .env file for configuration
require('dotenv').config({ path: 'rest-api-recipes/.env' });

// Import the function to obtain a bearer token from the authenticate-bearer module
const getBearerToken = require('./authenticate-bearer');

// Import Axios for making HTTP requests
const axios = require('axios');

// Load use-case specific variables from environment variables
const newMemberType = process.env.NEW_MEMBER_TYPE; // The new account type you want to assign
const memberId = process.env.MEMBERID; // The unique identifier of the member whose type you want to update
const baseURL = process.env.baseURL; // Your base URL

// Define an asynchronous function to update a member's account type
async function updateMemberAccountType() {
  // Obtain a bearer token using the imported getBearerToken function
  const accessToken = await getBearerToken();
  if (!accessToken) {
    // Log a message and exit if no token could be obtained
    console.log('Failed to obtain Bearer token.');
    return;
  }

  try {
    // Make a PATCH request to the API to update the member's account type
    // Construct the request URL using the base URL and member ID
    // Include the accessToken in the Authorization header for authentication
    const response = await axios.patch(`${baseURL}/members/${memberId}`, {
      memberType: newMemberType, // Data payload for the PATCH request
    }, {
      headers: {
        'Content-Type': 'application/json', // Indicate that the request body is JSON
        'Authorization': `Bearer ${accessToken}` // Authenticate the request
      }
    });

    // Log the response data to indicate success
    console.log('User account type updated successfully:', JSON.stringify(response.data, null, 2));
  } catch (error) {
    // Log detailed error information if the request fails
    console.error('Error updating member account type:', error.response ? error.response.data : error);
  }
}

// Execute the function to update a member's account type
updateMemberAccountType();
