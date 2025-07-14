// File: embedding_qs_series_2_api_use_cases/server/server.js

const express = require("express");
const dotenv = require("dotenv");
const path = require("path");
const { lookupMemberId, provisionEmbedUser } = require("../helpers/provision");

dotenv.config(); // Ensure .env is loaded

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware to support JSON and query string parsing
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// API ROUTES
app.use("/api/workbooks", require("../routes/api/workbooks"));
app.use("/api/pages", require("../routes/api/pages"));
app.use("/api/elements", require("../routes/api/elements"));
app.use("/api/jwt", require("../routes/api/jwt"));
app.use("/api/bookmarks", require("../routes/api/bookmarks"));

// GET /provision-users — One-time provisioning for build/view users
app.get("/provision-users", async (req, res) => {
  try {
    const result = {
      build: {
        email: process.env.BUILD_EMAIL,
        accountType: "Build",
        memberId: await provisionEmbedUser(
          process.env.BUILD_EMAIL,
          "Build",
          "QuickStarts",
          "Build"
        ),
      },
      view: {
        email: process.env.VIEW_EMAIL,
        accountType: "View",
        memberId: await provisionEmbedUser(
          process.env.VIEW_EMAIL,
          "View",
          "QuickStarts",
          "View"
        ),
      },
      admin: {
        email: process.env.ADMIN_EMAIL,
        memberId: await lookupMemberId(process.env.ADMIN_EMAIL),
      },
    };

    res.json(result);
  } catch (err) {
    console.error("Provisioning error:", err.message);
    res.status(500).json({ error: err.message });
  }
});

// Basic health check
app.get("/health", (req, res) => {
  res.send("Server is running");
});

// GET /env — Return key config values to client
app.get("/env", (req, res) => {
  res.json({
    DEBUG: process.env.DEBUG,
    BUILD_EMAIL: process.env.BUILD_EMAIL || "",
    VIEW_EMAIL: process.env.VIEW_EMAIL || "",
    ADMIN_EMAIL: process.env.ADMIN_EMAIL || "",
  });
});

// Static files
app.use(express.static(path.join(__dirname, "..", "public")));

// Debug route
app.get("/debug-test", (req, res) => {
  console.log("/debug-test hit");
  res.send("Debug route works");
});

// Start server
app.listen(PORT, () => {
  console.log(`Server running at http://localhost:${PORT}`);
});
