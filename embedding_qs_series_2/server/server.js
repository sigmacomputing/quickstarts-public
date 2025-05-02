// server/server.js

const express = require('express');
const dotenv = require('dotenv');
const path = require('path');
const { generateSignedUrl } = require('../helpers/embed-api');

dotenv.config();

const app = express();
const PORT = process.env.PORT || 3000;

// Dynamic JWT generation based on mode
app.get('/generate-jwt/:mode', async (req, res) => {
  try {
    const mode = req.params.mode;
    const { signedUrl, jwt } = await generateSignedUrl(mode); 
    res.json({ embedUrl: signedUrl, jwt: jwt });
  } catch (error) {
    console.error('Error generating signed URL with mode:', error);
    res.status(500).json({ error: 'JWT generation failed' });
  }
});

// Serve static files
app.use(express.static(path.join(__dirname, '..', 'public')));

// Health check
app.get('/health', (req, res) => {
  res.send('Server is running!');
});

// Start server
app.listen(PORT, () => {
  console.log(`Server listening at http://localhost:${PORT}`);
});
