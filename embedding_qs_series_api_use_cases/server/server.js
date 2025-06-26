// server/server.js

const express = require('express');
const dotenv = require('dotenv');
const path = require('path');
const { generateSignedUrl } = require('../helpers/embed-api');

dotenv.config();

const app = express();
const PORT = process.env.PORT || 3000;

// Dynamic JWT generation endpoint
// Required for link sharing: passes query params like exploreKey/bookmarkId to the JWT signer
app.get('/generate-jwt/:mode', async (req, res) => {
  try {
    const mode = req.params.mode;
    const { signedUrl, jwt } = await generateSignedUrl(mode, req.query);
    res.json({ embedUrl: signedUrl, jwt: jwt });
  } catch (error) {
    console.error('Error generating signed URL with mode:', error);
    res.status(500).json({ error: 'JWT generation failed' });
  }
});

// Optional endpoint: expose the base URL for public access embedding (if needed by frontend)
app.get('/generate-public-url', (req, res) => {
  res.json({ baseUrl: process.env.PUBLIC_ACCESS_BASE_URL });
});

// Serves HTML, CSS, JS, and assets from public folder
app.use(express.static(path.join(__dirname, '..', 'public')));

// Basic health check endpoint
app.get('/health', (req, res) => {
  res.send('Server is running!');
});

// Start the server
app.listen(PORT, () => {
  console.log(`Server listening at http://localhost:${PORT}`);
});
