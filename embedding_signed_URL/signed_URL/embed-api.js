// SIGMA SERVER-SIDE EMBED API - SECURE QUICKSTART

// 1: Require necessary Node.js modules
const express = require("express");
const crypto = require("crypto");
require("dotenv").config(); // Load environment variables

// 2: Initialize an Express application
const app = express();

// 3: Fetch configuration variables from .env file
const {
  CLIENT_ID,
  EMBED_SECRET,
  EMBED_PATH,
  EMAIL,
  EXTERNAL_USER_ID,
  EXTERNAL_USER_TEAM,
  ACCOUNT_TYPE,
  MODE,
  SESSION_LENGTH,
  PORT = 3000
} = process.env;

// 4: Log configuration details for debugging
console.log("Starting Sigma Server-Side Embed API Secure QuickStart");
console.log("Configuration details:");
console.log("CLIENT_ID:", CLIENT_ID);
console.log("EMAIL:", EMAIL);
console.log("EXTERNAL_USER_ID:", EXTERNAL_USER_ID);
console.log("EXTERNAL_USER_TEAM:", EXTERNAL_USER_TEAM);
console.log("ACCOUNT_TYPE:", ACCOUNT_TYPE);
console.log("MODE:", MODE);
console.log("SESSION_LENGTH:", SESSION_LENGTH);
console.log("EMBED_PATH:", EMBED_PATH);
console.log("PORT:", PORT);

// 5: Serve the main HTML file for the root path
app.get("/", (req, res) => {
  res.sendFile(`${__dirname}/index.html`);
});

// 6: Define a route handler for generating Sigma embed URLs
app.get("/api/generate-embed-url", (req, res) => {
  try {
    const nonce = crypto.randomUUID();
    const time = Math.floor(new Date().getTime() / 1000); // Current time in seconds

    // Build search parameters from environment variables
    let searchParams = `?:nonce=${nonce}&:client_id=${CLIENT_ID}&:email=${EMAIL}&:external_user_id=${EXTERNAL_USER_ID}&:external_user_team=${EXTERNAL_USER_TEAM}&:account_type=${ACCOUNT_TYPE}&:mode=${MODE}&:session_length=${SESSION_LENGTH}&:time=${time}`;

    // Construct the full URL with search parameters
    const URL_WITH_SEARCH_PARAMS = EMBED_PATH + searchParams;

    // Generate signature for the URL
    const SIGNATURE = crypto
      .createHmac("sha256", Buffer.from(EMBED_SECRET, "utf8"))
      .update(Buffer.from(URL_WITH_SEARCH_PARAMS, "utf8"))
      .digest("hex");

    const URL_TO_SEND = `${URL_WITH_SEARCH_PARAMS}&:signature=${SIGNATURE}`;

    // Log each parameter on a new line for debugging
    console.log("Generated Embed URL:");
    console.log(EMBED_PATH);
    searchParams.split("&").forEach(param => {
      console.log(param.replace("?:", "&:"));
    });
    console.log(`&:signature=${SIGNATURE}`);

    // Send the final URL to the requester
    res.status(200).json({ url: URL_TO_SEND });
  } catch (error) {
    console.error("Error generating embed URL:", error.message);
    res.status(500).send("Internal Server Error");
  }
});

// 7: Start the server
app.listen(PORT, () => {
  console.log(`Server listening on port ${PORT}`);
});