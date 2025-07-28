// helpers/local-wb-descriptions-store.js

const low = require("lowdb");
const FileSync = require("lowdb/adapters/FileSync");
const adapter = new FileSync("data/wb-descriptions.json");
const db = low(adapter);

// Default structure
db.defaults({ workbookDescriptions: [] }).write();

module.exports = db;