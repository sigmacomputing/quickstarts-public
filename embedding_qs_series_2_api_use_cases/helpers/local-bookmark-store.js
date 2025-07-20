// helpers/local-bookmark-store.js

const low = require("lowdb");
const FileSync = require("lowdb/adapters/FileSync");
const adapter = new FileSync("data/bookmarks.json"); // or another path
const db = low(adapter);

// Default structure
db.defaults({ bookmarks: [] }).write();

module.exports = db;
