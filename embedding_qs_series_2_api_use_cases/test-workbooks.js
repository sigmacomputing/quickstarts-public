// test-workbooks.js
const { getWorkbooksByTeam } = require("./helpers/get-workbooks");

(async () => {
  try {
    const result = await getWorkbooksByTeam("Embed_Users");
    console.log("✅ Workbooks:", result);
  } catch (e) {
    console.error("❌ Error during workbook fetch:", e.message);
  }
})();
