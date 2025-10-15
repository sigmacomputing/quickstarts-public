// File: plugin_use_cases/server/server.js
// Main Express server for Sigma Plugin Use Cases

const express = require("express");
const dotenv = require("dotenv");
const path = require("path");

// Load environment variables
require("dotenv").config();

// Initialize debug mode from environment
const DEBUG = process.env.DEBUG === "true";

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware to support JSON and query string parsing
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// API ROUTES
app.use("/api/jwt", require("../routes/api/jwt"));
app.use("/api/bookmarks", require("../routes/api/bookmarks"));
app.use("/api/multi-area-bookmarks", require("../routes/api/multi-area-bookmarks"));

// Basic health check
app.get("/health", (req, res) => {
  res.send("Plugin Host Server is running");
});

// GET /env — Return key config values to client
app.get("/env.json", (req, res) => {
  res.json({
    DEBUG: process.env.DEBUG,
    BUILD_EMAIL: process.env.BUILD_EMAIL || "",
    VIEW_EMAIL: process.env.VIEW_EMAIL || "",
    ADMIN_EMAIL: process.env.ADMIN_EMAIL || "",
    BUILD_ACCOUNT_TYPE: process.env.BUILD_ACCOUNT_TYPE || "Build",
    VIEW_ACCOUNT_TYPE: process.env.VIEW_ACCOUNT_TYPE || "View",
    
    // Application Constants
    ORG_SLUG: process.env.ORG_SLUG,
    WORKBOOK_NAME: process.env.WORKBOOK_NAME,
    EMBED_URL_BASE: process.env.EMBED_URL_BASE,
    PLUGIN_NAME: process.env.PLUGIN_NAME,

    // Plugin-specific Embed Parameters
    PLUGIN_MODE: process.env.PLUGIN_MODE,
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
    RESPONSIVE_HEIGHT: process.env.RESPONSIVE_HEIGHT,
    THEME: process.env.THEME,
  });
});

// Static files
app.use(express.static(path.join(__dirname, "..", "public")));

// Debug route - only active when DEBUG is enabled
app.get("/debug-test", (req, res) => {
  if (DEBUG) console.log("/debug-test hit");
  res.send("Debug route works");
});

// Start server
app.listen(PORT, () => {
  console.log(`Sigma Plugin Host server running at http://localhost:${PORT}`);
  if (DEBUG) console.log("Debug mode is enabled");
  console.log(`Plugin: ${process.env.PLUGIN_NAME || 'Not configured'}`);
});