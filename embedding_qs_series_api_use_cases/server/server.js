// server/server.js

const express = require("express");
const path = require("path");
const generateEmbedPath = require("../helpers/generateEmbedPath");

const app = express();
const PORT = process.env.PORT || 3000;

// Serve static files from the public folder
app.use(express.static(path.join(__dirname, "..", "public")));

// Embed URL generator using impersonation
app.get("/embed-url", async (req, res) => {
  const memberId = req.query.memberId;
  if (!memberId) {
    return res.status(400).json({ error: "Missing memberId parameter" });
  }

  try {
    const path = await generateEmbedPath(memberId);
    res.json({ path });
  } catch (err) {
    res.status(500).json({ error: "Failed to generate embed path" });
  }
});

// Endpoint to provision users and return their memberIds
const { lookupMemberId, provisionEmbedUser } = require("../helpers/provision");
const config = require("../helpers/config");

// Endpoint to provision users for embedding
app.get("/provision-users", async (req, res) => {
  try {
    const result = {};

    // Admin (must exist)
    result.admin = {
      email: config.email,
      memberId: await lookupMemberId(config.email),
    };

    // Build and View (auto-provision)
    result.build = {
      email: "build@test.com",
      accountType: "Build",
      memberId: await provisionEmbedUser("build@test.com", "Build"),
    };

    result.view = {
      email: "view@test.com",
      accountType: "View",
      memberId: await provisionEmbedUser("view@test.com", "View"),
    };

    res.json(result);
  } catch (err) {
    console.error("Provisioning error:", err.message);
    res.status(500).json({ error: err.message });
  }
});

// Start the server
app.listen(PORT, () => {
  console.log(`🚀 Server running at http://localhost:${PORT}`);
});
