// routes/api/provision-users.js

const express = require("express");
const router = express.Router();
const {
  lookupMemberId,
  provisionEmbedUser,
} = require("../../helpers/provision");

router.get("/", async (req, res) => {
  console.log("DELETE route hit");
  try {
    const adminEmail = process.env.ADMIN_EMAIL;
    const buildEmail = process.env.BUILD_EMAIL;
    const viewEmail = process.env.VIEW_EMAIL;

    if (!adminEmail || !buildEmail || !viewEmail) {
      return res.status(400).json({
        error:
          "Missing one or more required env vars: ADMIN_EMAIL, BUILD_EMAIL, VIEW_EMAIL",
      });
    }

    const [adminId, buildId, viewId] = await Promise.all([
      lookupMemberId(adminEmail),
      provisionEmbedUser(buildEmail, "Build", "User", "builder"),
      provisionEmbedUser(viewEmail, "View", "User", "viewer"),
    ]);

    res.json({
      admin: { email: adminEmail, memberId: adminId },
      build: { email: buildEmail, memberId: buildId },
      view: { email: viewEmail, memberId: viewId },
    });
  } catch (err) {
    console.error("Provisioning failed:", err);
    res.status(500).json({ error: "Provisioning failed" });
  }
});

module.exports = router;
