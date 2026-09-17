// File: embedding_qs_series_2_api_use_cases/routes/api/agents.js
// Thin proxy for the Sigma Agent API (Public Beta):
// https://help.sigmacomputing.com/docs/call-agents-with-the-api

const express = require("express");
const router = express.Router();
const axios = require("axios");
const getBearerToken = require("../../helpers/get-access-token");

const DEBUG = process.env.DEBUG === "true";

async function getSigmaHeaders() {
  const token = await getBearerToken();
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
}

function forwardError(res, err, fallbackMessage) {
  if (DEBUG) {
    console.error(fallbackMessage, err.response?.data || err.message);
  }
  const status = err.response?.status || 500;
  const message = err.response?.data?.message || fallbackMessage;
  res.status(status).json({ error: message });
}

// GET /api/agents/all — every agent accessible across the org
// Sigma API: GET /v2/workbookAgents
router.get("/all", async (req, res) => {
  try {
    const headers = await getSigmaHeaders();
    const response = await axios.get(`${process.env.BASE_URL}/workbookAgents`, {
      headers,
    });
    res.json(response.data);
  } catch (err) {
    forwardError(res, err, "Failed to list org agents");
  }
});

// GET /api/agents/workbook/:workbookId — agents scoped to one workbook
// Sigma API: GET /v2/workbooks/{workbookId}/agents
router.get("/workbook/:workbookId", async (req, res) => {
  try {
    const headers = await getSigmaHeaders();
    const { workbookId } = req.params;
    const response = await axios.get(
      `${process.env.BASE_URL}/workbooks/${workbookId}/agents`,
      { headers }
    );
    res.json(response.data);
  } catch (err) {
    forwardError(res, err, "Failed to list workbook agents");
  }
});

// POST /api/agents/:workbookId/:agentId/run — call an agent
// Sigma API: POST /v2/workbooks/{workbookId}/agents/{agentId}
// Body is forwarded as-is (messages, stream, responseFormat, maxTurns, etc.)
// so the client controls the exact request shape sent to Sigma.
router.post("/:workbookId/:agentId/run", async (req, res) => {
  const { workbookId, agentId } = req.params;
  const url = `${process.env.BASE_URL}/workbooks/${workbookId}/agents/${agentId}`;

  try {
    const headers = await getSigmaHeaders();

    if (req.body?.stream) {
      const upstream = await axios.post(url, req.body, {
        headers,
        responseType: "stream",
      });

      res.setHeader(
        "Content-Type",
        upstream.headers["content-type"] || "text/event-stream"
      );

      upstream.data.pipe(res);
      upstream.data.on("error", (err) => {
        if (DEBUG) console.error("Agent stream error:", err.message);
        res.end();
      });
    } else {
      const response = await axios.post(url, req.body, { headers });
      res.json(response.data);
    }
  } catch (err) {
    if (res.headersSent) {
      // Streaming response was already in progress when the upstream failed.
      res.end();
      return;
    }
    forwardError(res, err, "Agent call failed");
  }
});

module.exports = router;
