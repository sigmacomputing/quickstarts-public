// server/server.js

const express = require("express");
const dotenv = require("dotenv");
const path = require("path");
const { generateSignedUrl } = require("../helpers/embed-api");
const { lookupMemberId, provisionEmbedUser } = require("../helpers/provision");
const config = require("../helpers/config");

dotenv.config();

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware to support JSON and query string parsing
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// GET /generate-jwt/:mode — Signed URL with optional query params
app.get("/generate-jwt/:mode", async (req, res) => {
  try {
    const { mode } = req.params;
    const { signedUrl, jwt } = await generateSignedUrl(mode, req.query);
    res.json({ embedUrl: signedUrl, jwt });
  } catch (error) {
    console.error("❌ Error generating signed URL:", error);
    res.status(500).json({ error: "JWT generation failed" });
  }
});

// GET /provision-users — One-time provisioning for build/view users
app.get("/provision-users", async (req, res) => {
  try {
    const result = {
      build: {
        email: config.buildEmail,
        accountType: "Build",
        memberId: await provisionEmbedUser(
          config.buildEmail,
          "Build",
          "QuickStarts",
          "Build"
        ),
      },
      view: {
        email: config.viewEmail,
        accountType: "View",
        memberId: await provisionEmbedUser(
          config.viewEmail,
          "View",
          "QuickStarts",
          "View"
        ),
      },
      admin: {
        email: config.email,
        memberId: await lookupMemberId(config.email),
      },
    };

    res.json(result);
  } catch (err) {
    console.error("❌ Provisioning error:", err.message);
    res.status(500).json({ error: err.message });
  }
});

// Basic health check
app.get("/health", (req, res) => {
  res.send("Server is running!");
});

// GET /env — Return key config values to client
app.get("/env", (req, res) => {
  res.json({
    BUILD_EMAIL: config.buildEmail || "",
    VIEW_EMAIL: config.viewEmail || "",
    ADMIN_EMAIL: config.email || "",
  });
});

// Serve static assets
app.use(express.static(path.join(__dirname, "..", "public")));

// Start server
app.listen(PORT, () => {
  console.log(`🚀 Server running at http://localhost:${PORT}`);
});
