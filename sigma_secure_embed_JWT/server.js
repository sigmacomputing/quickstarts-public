const express = require('express');
const path = require('path');
const dotenv = require('dotenv');
const { generateSignedUrl } = require('./embed-api.js'); // Import the function from embed-api.js

dotenv.config();

const app = express();
const PORT = process.env.PORT || 3000;

// Set the view engine to EJS
app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, '/views')); // __dirname is automatically available

// Serve the index.html file with EJS
app.get('/', async (req, res) => {
    const signedEmbedUrl = await generateSignedUrl('user@example.com');
    res.render('index', { signedEmbedUrl });
});

// Start the server
app.listen(PORT, () => {
    console.log('Received request for /');
    console.log(`Server is running on http://localhost:${PORT}`);
});