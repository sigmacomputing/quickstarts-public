const express = require('express');
const jwt = require('jsonwebtoken');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const { sigma, resolveIds, getEmbedMember, listSavedWorkbooks } = require('../helpers/sigma');
const { presets } = require('../helpers/presets');
const { listLibraryElements, buildDocument } = require('../helpers/spec');

const router = express.Router();
const statePath = path.join(__dirname, '..', '.generated.json');

const readState = () => (fs.existsSync(statePath) ? JSON.parse(fs.readFileSync(statePath)) : {});
const writeState = (s) => fs.writeFileSync(statePath, JSON.stringify(s));

async function getLibrary() {
  const { libraryWorkbookId } = await resolveIds();
  return (await sigma('get', `/v2/workbooks/${libraryWorkbookId}/spec`)).document;
}

router.get('/presets', (req, res) => res.json(presets));

router.get('/library', async (req, res, next) => {
  try {
    res.json(listLibraryElements(await getLibrary()));
  } catch (e) {
    next(e);
  }
});

// First call creates the workbook; later calls update the same workbook in place.
router.post('/generate', async (req, res, next) => {
  try {
    const { presetId, placements } = req.body;
    const { folderId } = await resolveIds();
    const document = buildDocument(await getLibrary(), presetId, placements);
    const { workbookId } = readState();

    if (workbookId) {
      try {
        await sigma('put', `/v2/workbooks/${workbookId}/spec`, { document });
        return res.json({ workbookId, created: false });
      } catch (e) {
        // The saved workbook is gone or archived: fall through and create a new one.
        if (!e.response || ![400, 404, 409].includes(e.response.status)) throw e;
      }
    }
    const created = await sigma('post', '/v2/workbooks/spec', { name: 'Layout Composer Result', folderId, document });
    writeState({ workbookId: created.workbookId });
    res.json({ workbookId: created.workbookId, created: true });
  } catch (e) {
    next(e);
  }
});

router.get('/saved', async (req, res, next) => {
  try {
    res.json(await listSavedWorkbooks());
  } catch (e) {
    next(e);
  }
});

// Save a copy of the generated workbook to the embed user's My Documents.
router.post('/save', async (req, res, next) => {
  try {
    const { workbookId } = readState();
    if (!workbookId) return res.status(404).json({ error: 'Generate a layout first.' });
    const name = (req.body.name || '').trim();
    if (!name) return res.status(400).json({ error: 'A name is required.' });
    const { homeFolderId } = await getEmbedMember();
    const copy = await sigma('post', `/v2/workbooks/${workbookId}/copy`, { name, destinationFolderId: homeFolderId });
    res.json({ workbookId: copy.workbookId, name });
  } catch (e) {
    next(e);
  }
});

// Signed embed URL for the generated workbook. Returns url: null until embed settings are in .env.
router.get('/embed-url', async (req, res, next) => {
  try {
    let { workbookId } = readState();
    if (req.query.workbookId) {
      const saved = await listSavedWorkbooks();
      if (!saved.some((w) => w.workbookId === req.query.workbookId)) return res.status(404).json({ error: 'Saved workbook not found.' });
      workbookId = req.query.workbookId;
    }
    if (!workbookId) return res.status(404).json({ error: 'No workbook has been generated yet.' });

    const { ORG_SLUG, EMBED_EMAIL, EMBED_ACCOUNT_TYPE, EMBED_TEAMS, EMBED_URL_BASE, CLIENT_ID, SECRET } = process.env;
    const workbook = await sigma('get', `/v2/workbooks/${workbookId}`);
    const base = EMBED_URL_BASE || 'https://app.sigmacomputing.com';
    const workbookUrl = `${base}/${ORG_SLUG || ''}/workbook/${workbook.workbookUrlId}`;
    if (!ORG_SLUG || !EMBED_EMAIL) return res.json({ url: null, workbookUrl: workbook.url });

    const now = Math.floor(Date.now() / 1000);
    const token = jwt.sign(
      {
        sub: EMBED_EMAIL,
        iss: CLIENT_ID,
        jti: crypto.randomUUID(),
        iat: now,
        exp: now + 3600,
        account_type: EMBED_ACCOUNT_TYPE || 'View',
        teams: (EMBED_TEAMS || '').split(',').map((t) => t.trim()).filter(Boolean),
      },
      SECRET,
      { algorithm: 'HS256', keyid: CLIENT_ID }
    );
    res.json({ url: `${workbookUrl}?:embed=true&:jwt=${token}`, workbookUrl });
  } catch (e) {
    next(e);
  }
});

module.exports = router;
