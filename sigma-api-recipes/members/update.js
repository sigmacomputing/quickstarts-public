// This script will update the account type for a member, based on the memberId defined in the .env file

// 1: Load environment variables from a specific .env file for configuration
require('dotenv').config({ path: 'rest-api-recipes/.env' });

// 2: Import the function to obtain a bearer token from the authenticate-bearer module
const getBearerToken = require('../get-access-token');

// 3: Import Axios for making HTTP requests
const axios = require('axios');

// 4: Load use-case specific variables from environment variables
const newMemberType = process.env.NEW_MEMBER_TYPE; // The new account type you want to assign
const memberId = process.env.MEMBERID; // The unique identifier of the member whose type you want to update
const baseURL = process.env.baseURL; // Your base URL

// Define an asynchronous function to update a member's account type
async function updateMemberAccountType() {
  const accessToken = await getBearerToken();
  if (!accessToken) {
    console.log('Failed to obtain Bearer token.');
    return;
  }

  try {
    // Construct the request URL using the base URL and member ID
    const requestURL = `${baseURL}/members/${memberId}`;
    
    // Log the constructed URL before sending the request
    console.log(`URL sent to Sigma: ${requestURL}`);

    // Make a PATCH request to the API to update the member's account type
    const response = await axios.patch(requestURL, {
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