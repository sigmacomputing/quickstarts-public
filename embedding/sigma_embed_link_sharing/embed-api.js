// SIGMA EMBED LINK SHARING QUICKSTART
// embed-api.js

// 1: Require necessary Node.js modules
const express = require("express");
const crypto = require("crypto");
require("dotenv").config(); // Load environment variables from .env file

// 2: Initialize an Express application
const app = express();

// 3: Fetch configuration variables from .env file
const EMBED_PATH = process.env.EMBED_PATH;  // Base URL for Sigma embedding
const EXPLORE_EMBED_PATH = process.env.EXPLORE_EMBED_PATH;  // Base URL for exploration embedding
const EMBED_SECRET = process.env.EMBED_SECRET;  // Secret key for signing the embed URL
const CLIENT_ID = process.env.CLIENT_ID;  // Client ID for Sigma API
const EMAIL = process.env.EMAIL;  // Email associated with the Sigma user
const EXTERNAL_USER_ID = process.env.EXTERNAL_USER_ID;  // External user ID
const EXTERNAL_USER_TEAM = process.env.EXTERNAL_USER_TEAM;  // Team associated with the external user
const ACCOUNT_TYPE = process.env.ACCOUNT_TYPE;  // Account type (e.g., viewer, creator)
const MODE = process.env.MODE;  // Mode (e.g., userbacked)
const SESSION_LENGTH = process.env.SESSION_LENGTH;  // Session length in seconds
const PORT = process.env.PORT || 3000;  // Default port is 3000

// 4: Serve static files from the root directory
app.use(express.static(__dirname));  // Serve index.html and other static files

// 5: Define a route handler for generating Sigma embed URLs
app.get("/api/generate-embed-url", (req, res) => {
    try {
        // Generate a unique nonce using crypto's UUID
        const nonce = crypto.randomUUID();
        let searchParams = `?:nonce=${nonce}`;

        // Add required search parameters using .env variables
        searchParams += `&:client_id=${CLIENT_ID}`;
        searchParams += `&:email=${EMAIL}`;
        searchParams += `&:external_user_id=${EXTERNAL_USER_ID}`;
        searchParams += `&:external_user_team=${EXTERNAL_USER_TEAM}`;
        searchParams += `&:account_type=${ACCOUNT_TYPE}`;
        searchParams += `&:mode=${MODE}`;
        searchParams += `&:session_length=${SESSION_LENGTH}`;
        searchParams += `&:time=${Math.floor(new Date().getTime() / 1000)}`;  // Current time in seconds

        // Handle exploreKey if present in the query parameters
        const exploreKey = req.query.exploreKey;

        // Append exploreKey to the URL if present
        if (exploreKey) {
            searchParams += `&:explore=${exploreKey}`;
        }

        // Handle bookmarkId if present in the query parameters
        const bookmarkId = req.query.bookmarkId;

        // Append bookmarkId to the URL if present
        if (bookmarkId) {
            searchParams += `&:bookmark=${bookmarkId}`;
        }

        // Construct the URL with search parameters and generate a signature
        const URL_WITH_SEARCH_PARAMS = EMBED_PATH + searchParams;
        const SIGNATURE = crypto
            .createHmac("sha256", Buffer.from(EMBED_SECRET, "utf8"))
            .update(Buffer.from(URL_WITH_SEARCH_PARAMS, "utf8"))
            .digest("hex");
        const URL_TO_SEND = `${URL_WITH_SEARCH_PARAMS}&:signature=${SIGNATURE}`;

        // Send the final URL to the requester
        res.status(200).json({ url: URL_TO_SEND });
    } catch (error) {
        // Log and send error if URL generation fails
        console.error("Error generating embed URL:", error.message);
        res.status(500).send("Internal Server Error");
    }
});

// 6: Define a route to serve the exploration embed URL from .env
app.get("/api/get-explore-embed-url", (req, res) => {
    try {
        const exploreEmbedUrl = EXPLORE_EMBED_PATH;
        res.status(200).json({ url: exploreEmbedUrl });
    } catch (error) {
        // Log and send error if retrieval fails
        console.error("Error retrieving explore embed URL:", error.message);
        res.status(500).send("Internal Server Error");
    }
});

// 7: Start the server
app.listen(PORT, () => {
    console.log(`Node Express Server listening on port ${PORT}`);
});
