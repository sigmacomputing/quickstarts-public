// Import required modules
const express = require('express');        // Express is a minimal web framework for Node.js
const path = require('path');              // Path module provides utilities for working with file and directory paths
const dotenv = require('dotenv');          // Dotenv loads environment variables from a .env file into process.env
const { generateSignedUrl } = require('./embed-api.js'); // Import the generateSignedUrl function from embed-api.js

// Load environment variables from the .env file into process.env
dotenv.config();

// Initialize the Express application
const app = express();
const PORT = process.env.PORT || 3000;     // Set the port number from environment variables or default to 3000

// Configure Express to use EJS as the templating engine
app.set('view engine', 'ejs');             // Set EJS as the view engine
app.set('views', path.join(__dirname, '/views')); // Set the directory where the view templates (EJS files) are located

// Define the root route to serve the index.ejs file
app.get('/', async (req, res) => {
    // Generate a signed URL for the Sigma embed
    const signedEmbedUrl = await generateSignedUrl('user@example.com'); // Call the generateSignedUrl function, passing in an email address

    // Render the index.ejs template, passing the signedEmbedUrl to the template
    res.render('index', { signedEmbedUrl }); // Render the 'index' view (index.ejs) and pass the signed URL as a variable to the template
});

// Start the Express server
app.listen(PORT, () => {
    console.log('Received request for /'); // Log a message when the root route is accessed
    console.log(`Server is running on http://localhost:${PORT}`); // Log a message indicating the server is running and on which port
});