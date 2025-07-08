const express = require("express");
const router = express.Router();

const buildEmbedUrl = require("../../helpers/build-embed-url");
const getWorkbookMetadata = require("../../helpers/get-workbook-metadata");
const generateJwt = require("../../helpers/create-jwt");

/**
 * Sigma API: GET /v2/workbooks/{workbookId}
 * This endpoint is used to fetch workbook metadata including:
 * - orgSlug
 * - workbookName
 * - validated workbookUrlId
 *
 * This route generates a JWT + Sigma embed URL based on the user's selection.
 * The JWT is signed server-side and returned to the frontend along with the full embed URL.
 */

router.post("/:mode", async (req, res) => {
  try {
    const { embedType = "workbook", workbookUrlId, targetId } = req.query;
    const mode = req.params.mode;
    const selectedUser = req.body?.sub || req.query?.sub;

    let pageId = "";
    let elementId = "";

    if (embedType === "element") {
      if (!targetId || !targetId.includes(":")) {
        return res
          .status(400)
          .json({ error: "Missing or invalid targetId for element embed" });
      }
      [pageId, elementId] = targetId.split(":");
    }

    if (!workbookUrlId) {
      return res.status(400).json({ error: "Missing workbookUrlId" });
    }

    // Map selected role (view/build) to email from .env
    const userMap = {
      view: process.env.VIEW_EMAIL,
      build: process.env.BUILD_EMAIL,
    };
    const sub = userMap[selectedUser] || selectedUser;

    // 🔹 Get workbook metadata from Sigma API (via helper)
    const metadata = await getWorkbookMetadata(workbookUrlId);
    if (!metadata) {
      return res.status(404).json({ error: "Workbook not found" });
    }

    const {
      orgSlug,
      workbookName,
      workbookUrlId: parsedWorkbookUrlId,
    } = metadata;

    // Defensive validation
    if (embedType === "page" && (!workbookName || !targetId)) {
      return res
        .status(400)
        .json({ error: "Missing workbookName or pageId for page embed" });
    }
    if (embedType === "element" && (!workbookName || !targetId)) {
      return res
        .status(400)
        .json({ error: "Missing workbookName or elementId for element embed" });
    }

    // 🔹 Construct embed URL from metadata
    const embedUrl = buildEmbedUrl({
      orgSlug,
      workbookName,
      workbookUrlId: parsedWorkbookUrlId,
      embedType,
      pageId: embedType === "page" ? targetId : pageId,
      elementId: embedType === "element" ? elementId : "",
    });

    // 🔹 Generate signed JWT
    const jwt = generateJwt({ embedUrl, mode, sub });

    // Optional: log final result for visibility
    console.log("Embed generated:", embedUrl);

    // res.json({ embedUrl: `${embedUrl}?:jwt=${jwt}`, jwt });
    const separator = embedUrl.includes("?") ? "&" : "?";
res.json({ embedUrl: `${embedUrl}${separator}:jwt=${jwt}`, jwt });

  } catch (err) {
    console.error("Failed to generate JWT:", err);
    res.status(500).json({ error: "Internal error" });
  }
});

module.exports = router;