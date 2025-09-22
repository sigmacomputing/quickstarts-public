// This script responds with a bearer token and is called from each of the other scripts in this project. 
// Variables are in .env and need to be updated for your Sigma hosted environment and API keys

// Swagger: https://help.sigmacomputing.com/reference/token

// 1: Load environment variables from a specific .env file for configuration
require('dotenv').config({ path: '.env' });

// 2: Import Axios for making HTTP requests
const axios = require('axios');

// 4: Load use-case specific variables from environment variables
const authURL = process.env.authURL; // The URL for your Sigma Instance
const clientId = process.env.CLIENT_ID; // Your client ID
const secret = process.env.SECRET; // Your API secret

// Asynchronous function to obtain a bearer token using the credentials grant type
async function getBearerToken() {
  try {
    // Prepare the data for the request using URLSearchParams to encode it as application/x-www-form-urlencoded
    const requestData = new URLSearchParams({
      grant_type: 'client_credentials', // Indicates the grant type for OAuth 2.0
      client_id: clientId, // Your client ID
      client_secret: secret, // Your client secret
    });

    // Log the constructed URL before sending the request
      console.log(`URL sent to Sigma: ${authURL}`);

    // Make a POST request to the authentication URL with the encoded data and headers
    const response = await axios.post(authURL, requestData, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded', // Ensure the server treats the sent data as URL-encoded form data
      },
    });

    // Log the success message and the obtained bearer token
    console.log('Bearer token obtained successfully:', response.data.access_token);
    return response.data.access_token; // Return the obtained token for use in subsequent API requests
  } catch (error) {
    // Log any errors that occur during the token acquisition process
    console.error('Error obtaining Bearer token:', error.response ? error.response.data : error.message);
    return null; // Return null to indicate that the token acquisition failed
  }
}

// Check if this script is being run directly and not imported as a module in another script. This is so we can run standalone and verify we get a token response.
if (require.main === module) {
    // Call getBearerToken and handle the promise it returns
    getBearerToken().then(token => {
        // Log the acquired token for verification
        console.log('Token acquired:', token);
    }).catch(error => {
        // Log any errors that occur when trying to acquire the token
        console.error('Failed to acquire token:', error);
    });
}

// Export the getBearerToken function to make it available for import in other use-case scripts
module.exports = getBearerToken;
