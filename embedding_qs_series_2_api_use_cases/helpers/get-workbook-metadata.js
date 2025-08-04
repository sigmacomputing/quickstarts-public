// File: embedding_qs_series_2_api_use_cases/helpers/get-workbook-metadata.js

const { getWorkbooksByTeam } = require("./get-workbooks");
const axios = require("axios");
const getBearerToken = require("./get-access-token");
const { lookupMemberId } = require("./provision");

module.exports = async function getWorkbookMetadata(workbookUrlId) {
  // First try the original team-based lookup for backwards compatibility
  try {
    const teamWorkbooks = await getWorkbooksByTeam();
    const teamMatch = teamWorkbooks.find((wb) =>
      wb.url?.endsWith(`/workbook/${workbookUrlId}`)
    );
    
    if (teamMatch) {
      if (process.env.DEBUG === "true") {
        console.log("Found workbook via team lookup:", teamMatch.name);
      }
      const urlParts = teamMatch.url.split("/");
      const orgSlug = urlParts[3];
      
      return {
        orgSlug,
        workbookName: teamMatch.name.replace(/\s+/g, "_"),
        workbookUrlId,
        workbookId: teamMatch.id,
        workbookVersion: teamMatch.latestVersion,
      };
    }
  } catch (error) {
    if (process.env.DEBUG === "true") {
      console.log("Team lookup failed, trying member-based lookup:", error.message);
    }
  }

  // If team lookup fails, try member-based lookup (same as dual dropdown filtering)
  try {
    if (process.env.DEBUG === "true") {
      console.log("Trying member-based workbook lookup for JWT generation");
    }
    
    const token = await getBearerToken();
    const headers = {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    };
    
    // Get the memberId for the embed user
    const embedUserEmail = process.env.BUILD_EMAIL;
    const memberId = await lookupMemberId(embedUserEmail);
    
    // Get all files accessible to this member
    const memberFilesUrl = `${process.env.BASE_URL}/members/${memberId}/files?typeFilters=workbook&limit=500`;
    const memberFilesResponse = await axios.get(memberFilesUrl, { headers });
    const memberFiles = memberFilesResponse.data.entries || [];
    const memberFileIds = memberFiles.map(file => file.id);
    
    // Get all workbooks and filter by accessibility
    const workbooksResponse = await axios.get(`${process.env.BASE_URL}/workbooks?limit=500`, { headers });
    const allWorkbooks = workbooksResponse.data.entries || [];
    
    const accessibleWorkbooks = allWorkbooks.filter(workbook => {
      return memberFileIds.includes(workbook.workbookId);
    });
    
    // Format workbooks to match expected structure
    const formattedWorkbooks = accessibleWorkbooks.map((w) => ({
      id: w.workbookId,
      urlId: w.workbookUrlId, 
      name: w.name,
      url: w.url,
      version: w.latestVersion,
      path: w.path,
      latestVersion: w.latestVersion,
    }));
    
    const match = formattedWorkbooks.find((wb) =>
      wb.url?.endsWith(`/workbook/${workbookUrlId}`)
    );
    
    if (match) {
      if (process.env.DEBUG === "true") {
        console.log("Found workbook via member lookup:", match.name);
      }
      const urlParts = match.url.split("/");
      const orgSlug = urlParts[3];
      
      return {
        orgSlug,
        workbookName: match.name.replace(/\s+/g, "_"),
        workbookUrlId,
        workbookId: match.id,
        workbookVersion: match.latestVersion,
      };
    }
  } catch (error) {
    if (process.env.DEBUG === "true") {
      console.log("Member-based lookup also failed:", error.message);
    }
  }

  // If both lookups fail, throw error
  throw new Error(`Workbook not found for workbookUrlId: ${workbookUrlId}`);
};
