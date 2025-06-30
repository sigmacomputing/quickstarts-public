// server/server.js

require("dotenv").config();
const express = require("express");
const jwt = require("jsonwebtoken");
const path = require("path");
const { v4: uuidv4 } = require("uuid");

const app = express();
const config = require("../helpers/config");
const { lookupMemberId, provisionEmbedUser } = require("../helpers/provision");

app.use(express.json());

// 1: Log all incoming requests
app.use((req, res, next) => {
  console.log(`📡 Incoming: ${req.method} ${req.url}`);
  next();
});

// 2: Validate required config
if (
  !config.email ||
  !config.clientId ||
  !config.secret ||
  !config.defaultWorkbookId ||
  !config.memberIds.view ||
  !config.memberIds.build
) {
  throw new Error("Missing one or more required values in .env or config.js");
}

const PORT = process.env.PORT || 3000;

// 3: Serve frontend
app.use(express.static(path.join(__dirname, "..", "public")));

// 4: Health check
app.get("/health", (req, res) => res.send("OK"));

// 5: POST /embed-url — Generate signed embed URL based on role or memberId
app.post("/embed-url", async (req, res) => {
  const { memberId, user } = req.body;
  console.log("📥 /embed-url body:", { memberId, user });

  let resolvedId = memberId;

  if (!resolvedId && user) {
    const role = user.toLowerCase();

    console.log("🔍 Checking config.memberIds for role:", role);
    console.log("🔍 Available roles in config:", config.memberIds);

    if (config.memberIds[role]) {
      resolvedId = config.memberIds[role];
    } else {
      return res.status(400).json({ error: "Invalid role passed." });
    }
  }

  if (!resolvedId) {
    return res.status(400).json({ error: "Missing or unresolvable memberId." });
  }

  try {
    const embedPath = new URL(config.defaultWorkbookId).pathname;
    const now = Math.floor(Date.now() / 1000);

    const payload = {
      sub: resolvedId,
      path: embedPath,
      exp: now + config.sessionLength,
      iat: now,
      iss: config.clientId,
      jti: uuidv4(),
      teams: config.teams,
    };

    const token = jwt.sign(payload, config.secret, {
      algorithm: "HS256",
      keyid: config.clientId,
    });

    const fullUrl = `${config.defaultWorkbookId}?auth_token=${token}`;

    console.log("🔗 Full Embed URL:", fullUrl);
    console.log("📦 Decoded JWT Payload:", payload);
    console.log("🔑 Signed Token:", token);

    res.json({ embedUrl: fullUrl });
  } catch (err) {
    console.error("❌ Error generating embed URL:", err.message);
    res.status(500).json({ error: err.message });
  }
});

// 6: GET /env — Return config values (for debugging only)
app.get("/env", (req, res) => {
  res.json({
    ADMIN_MEMBER_ID: config.memberIds.admin,
    BUILD_MEMBER_ID: config.memberIds.build,
    VIEW_MEMBER_ID: config.memberIds.view,
    EMBED_PATH: config.defaultWorkbookId,
  });
});

// 7: GET /provision-users — Create View/Build users if needed
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

// 8: Start server
app.listen(PORT, () => {
  console.log(`🚀 Server running at http://localhost:${PORT}`);
});
