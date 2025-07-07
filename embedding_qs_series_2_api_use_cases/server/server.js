// server/server.js

const express = require("express");
const dotenv = require("dotenv");
const path = require("path");
// const { generateSignedUrl } = require("../helpers/embed-api");
const { lookupMemberId, provisionEmbedUser } = require("../helpers/provision");

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware to support JSON and query string parsing
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

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
        email: process.env.email,
        memberId: await lookupMemberId(process.env.ADMIN_EMAIL),
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
    BUILD_EMAIL: process.env.BUILD_EMAIL || "",
    VIEW_EMAIL: process.env.VIEW_EMAIL || "",
    ADMIN_EMAIL: process.env.ADMIN_EMAIL || "",
  });
});

// Serve static assets
app.use(express.static(path.join(__dirname, "..", "public")));

// API ROUTES

// POST /generate-jwt — Generate JWT for embedding
const generateJwtRoute = require("../routes/api/generate-jwt");
app.use("/generate-jwt", generateJwtRoute);

//  GET /api/workbooks — Fetch workbooks by team
app.use("/api/get-workbooks", require("../routes/api/get-workbooks"));

//  GET /api/get-pages — Fetch pages from a specific workbook
app.use("/api/get-pages", require("../routes/api/get-pages"));

// GET /api/get-elements — Fetch elements from a specific workbook and page
app.use("/api/get-elements", require("../routes/api/get-elements"));

// DEBUGGING ROUTES
app.get("/debug-test", (req, res) => {
  console.log("🧪 /debug-test hit");
  res.send("Debug route works");
});


// Start server
app.listen(PORT, () => {
  console.log(`🚀 Server running at http://localhost:${PORT}`);
});
