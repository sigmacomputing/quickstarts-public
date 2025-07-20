// File: embedding_qs_series_2_api_use_cases/server/server.js

const express = require("express");
const dotenv = require("dotenv");
const path = require("path");
const { lookupMemberId, provisionEmbedUser } = require("../helpers/provision");
const DEBUG = process.env.DEBUG === "true";

require("dotenv").config();

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
app.use("/api/bookmarks_db", require("../routes/api/bookmarks_db"));

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
app.get("/env.json", (req, res) => {
  res.json({
    DEBUG: process.env.DEBUG,
    BUILD_EMAIL: process.env.BUILD_EMAIL || "",
    VIEW_EMAIL: process.env.VIEW_EMAIL || "",
    ADMIN_EMAIL: process.env.ADMIN_EMAIL || "",

    // Optional Embed Parameters
    DISABLE_AUTO_REFRESH: process.env.DISABLE_AUTO_REFRESH,
    DISABLE_MOBILE_VIEW: process.env.DISABLE_MOBILE_VIEW,
    HIDE_FOLDER_NAVIGATION: process.env.HIDE_FOLDER_NAVIGATION,
    HIDE_MENU: process.env.HIDE_MENU,
    HIDE_PAGE_CONTROLS: process.env.HIDE_PAGE_CONTROLS,
    HIDE_RELOAD_BUTTON: process.env.HIDE_RELOAD_BUTTON,
    HIDE_TITLE: process.env.HIDE_TITLE,
    HIDE_TOOLTIP: process.env.HIDE_TOOLTIP,
    HIDE_VIEW_SELECT: process.env.HIDE_VIEW_SELECT,
    LNG: process.env.LNG,
    MENU_POSITION: process.env.MENU_POSITION,
    PAGE_ID: process.env.PAGE_ID,
    RESPONSIVE_HEIGHT: process.env.RESPONSIVE_HEIGHT,
    THEME: process.env.THEME,
    VIEW_ID: process.env.VIEW_ID,
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
