// embed-api.js

const jwt = require('jsonwebtoken'); // Import jsonwebtoken library for handling JWTs
const { v4: uuid } = require('uuid'); // Import uuid for generating unique identifiers
const dotenv = require('dotenv'); // Import dotenv for loading environment variables

dotenv.config(); // Load environment variables from .env file

// Define constants for the embed URL and session length
const BASE_URL = process.env.BASE_URL;
const SESSION_LENGTH = Math.min(process.env.SESSION_LENGTH || 3600, 2592000); // Max 30 days in seconds

// Log important configuration details to ensure they are correctly set
console.log('BASE_URL:', BASE_URL);
console.log('SESSION_LENGTH:', SESSION_LENGTH);
console.log('EMBED_CLIENT_ID:', process.env.EMBED_CLIENT_ID); // Verify the client ID

// Function to generate a signed URL for embedding Sigma dashboards
async function generateSignedUrl() {
    try {
        // Retrieve the secret and email from environment variables
        const secret = process.env.EMBED_SECRET;
        const email = process.env.EMBED_EMAIL;
        const time = Math.floor(Date.now() / 1000); // Generate the current time as a Unix timestamp

        // Generate JWT with claims
        // See https://help.sigmacomputing.com/docs/create-an-embed-api-with-json-web-tokens for list of available claims
        const token = jwt.sign({
            sub: email, // Subject (the email of the user)
            iss: process.env.EMBED_CLIENT_ID, // Issuer (client ID)
            jti: uuid(), // JWT ID (unique identifier for the token)
            iat: time, // Issued at time (current time)
            exp: time + SESSION_LENGTH, // Expiration time (current time + session length)
            account_type: "lite", // Optional claim for account type
            teams: ["Sales_People"] // Optional claim for user teams
        }, secret, {
            algorithm: 'HS256', // Algorithm used for signing the JWT
            keyid: process.env.EMBED_CLIENT_ID // Key ID for the JWT header, should match Sigma's expectations
        });

        // Decode the JWT to inspect its content and log it
        const decodedToken = jwt.decode(token, { complete: true });
        console.log('Decoded JWT:', decodedToken); // Log the decoded JWT for debugging

        // Construct the signed embed URL by appending the JWT and embed parameters
        const signedEmbedUrl = `${BASE_URL}?:jwt=${token}&:embed=true`;

        // Log the constructed signed URL
        console.log('Signed Embed URL:', signedEmbedUrl);

        return signedEmbedUrl; // Return the signed embed URL
    } catch (error) {
        // Log any errors that occur during JWT generation
        console.error("Failed to generate JWT:", error);
        throw new Error("JWT generation failed"); // Throw an error if JWT generation fails
    }
}

// Export the generateSignedUrl function so it can be used in other files
module.exports = { generateSignedUrl };
