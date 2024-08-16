const jwt = require('jsonwebtoken');
const { v4: uuid } = require('uuid');
const dotenv = require('dotenv');

dotenv.config();

const BASE_URL = process.env.BASE_URL || 'https://app.sigmacomputing.com';
const EMBED_PATH = process.env.EMBED_PATH || '/embed/default-path';
const SESSION_LENGTH = Math.min(process.env.SESSION_LENGTH || 3600, 2592000); // Max 30 days in seconds

console.log('BASE_URL:', BASE_URL);
console.log('EMBED_PATH:', EMBED_PATH);
console.log('SESSION_LENGTH:', SESSION_LENGTH);
console.log('EMBED_CLIENT_ID:', process.env.EMBED_CLIENT_ID); // Add this to verify the client ID

async function generateSignedUrl() {
    try {
        const secret = process.env.EMBED_SECRET;
        const email = process.env.EMBED_EMAIL;
        const time = Math.floor(Date.now() / 1000); // Generate the current time as a Unix timestamp

        // Generate JWT with claims
        const token = jwt.sign({
            sub: email,
            iss: process.env.EMBED_CLIENT_ID,
            jti: uuid(),
            iat: time, // Issued at time
            exp: time + SESSION_LENGTH, // Expiration time, capped at 30 days
            account_type: "lite",
            teams: ["Sales_People"]
        }, secret, {
            algorithm: 'HS256',
            keyid: process.env.EMBED_CLIENT_ID // This needs to match what Sigma expects
        });

        // Construct the signed embed URL
        const signedEmbedUrl = `${BASE_URL}${EMBED_PATH}?:jwt=${token}&:embed=true`;

        console.log('Signed Embed URL:', signedEmbedUrl);

        return signedEmbedUrl;
    } catch (error) {
        console.error("Failed to generate JWT:", error);
        throw new Error("JWT generation failed");
    }
}

module.exports = { generateSignedUrl };