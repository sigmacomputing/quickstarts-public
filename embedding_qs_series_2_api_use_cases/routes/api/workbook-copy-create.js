const express = require("express");
const router = express.Router();
const axios = require("axios");
const getBearerToken = require("../../helpers/get-access-token");
const getEmbedUserToken = require("../../helpers/get-embed-user-token");
const { lookupMemberId } = require("../../helpers/provision");

const DEBUG = process.env.DEBUG === "true";

// Helper function to get Sigma API headers (using admin credentials)
async function getSigmaHeaders() {
  const token = await getBearerToken();
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
}

// Helper function to find the build user's My Documents folder ID
async function getBuildUserMyDocumentsFolderId() {
  try {
    const headers = await getSigmaHeaders();
    const embedUserEmail = process.env.BUILD_EMAIL;
    const memberId = await lookupMemberId(embedUserEmail);
    
    if (DEBUG) console.log(`Looking for My Documents folder for member: ${memberId}`);
    
    // Get all files accessible to the build user (including folders)
    const memberFilesUrl = `${process.env.BASE_URL}/members/${memberId}/files?limit=500`;
    if (DEBUG) console.log(`Fetching member files from: ${memberFilesUrl}`);
    
    const memberFilesResponse = await axios.get(memberFilesUrl, { headers });
    const memberFiles = memberFilesResponse.data.entries || [];
    
    if (DEBUG) console.log(`Found ${memberFiles.length} total files/folders for member`);
    if (DEBUG) {
      const folders = memberFiles.filter(f => f.type === "folder");
      console.log(`Folders available to member:`, folders.map(f => ({ name: f.name, path: f.path, id: f.id })));
    }
    
    // Look for the user's My Documents folder (more specific search)
    const myDocumentsFolder = memberFiles.find(file => 
      file.type === "folder" && 
      file.name === "My Documents" &&
      (file.path === "My Documents" || !file.path) // Root level or exact path match
    );
    
    if (myDocumentsFolder) {
      if (DEBUG) console.log(`Found build user's My Documents folder: ${myDocumentsFolder.id} (${myDocumentsFolder.name})`);
      return myDocumentsFolder.id;
    }
    
    // If not found in member files, try to find it through the general files API
    if (DEBUG) console.log("My Documents not found in member files, trying general files API");
    const allFilesResponse = await axios.get(`${process.env.BASE_URL}/files`, { headers });
    const allFiles = allFilesResponse.data.entries || [];
    
    if (DEBUG) {
      const myDocsOptions = allFiles.filter(file => 
        file.type === "folder" && 
        (file.name === "My Documents" || file.path?.includes("My Documents"))
      );
      console.log(`My Documents folder candidates:`, myDocsOptions.map(f => ({ name: f.name, path: f.path, id: f.id, ownerId: f.ownerId })));
    }
    
    const generalMyDocsFolder = allFiles.find(file => 
      file.type === "folder" && 
      file.name === "My Documents" &&
      file.ownerId === memberId && // Match the build user as owner
      (file.path === "My Documents" || !file.path) // Root level or exact path match
    );
    
    if (generalMyDocsFolder) {
      if (DEBUG) console.log(`Found build user's My Documents folder via general API: ${generalMyDocsFolder.id}`);
      return generalMyDocsFolder.id;
    }
    
    // Try the known folder ID as last resort
    const knownMyDocsFolderId = "rleTgkyUSzKwLRWNFK5tS";
    if (DEBUG) console.log(`Using known My Documents folder ID as fallback: ${knownMyDocsFolderId}`);
    
    // Verify this folder exists and is accessible
    try {
      const folderCheckUrl = `${process.env.BASE_URL}/files/${knownMyDocsFolderId}`;
      const folderCheck = await axios.get(folderCheckUrl, { headers });
      if (folderCheck.data && folderCheck.data.type === "folder") {
        if (DEBUG) console.log(`Verified known folder ID is valid: ${knownMyDocsFolderId}`);
        return knownMyDocsFolderId;
      }
    } catch (verifyError) {
      if (DEBUG) console.log(`Known folder ID verification failed: ${verifyError.message}`);
    }
    
    throw new Error("Could not find build user's My Documents folder");
  } catch (error) {
    if (DEBUG) console.error("Error finding build user's My Documents folder:", error.message);
    throw error;
  }
}

// GET /api/workbook-copy-create/my-documents-folder - Get the user's My Documents folder ID
router.get("/my-documents-folder", async (req, res) => {
  try {
    if (DEBUG) console.log("Finding build user's My Documents folder ID");

    const folderId = await getBuildUserMyDocumentsFolderId();
    
    res.json({ 
      folderId,
      folderName: "My Documents",
      folderPath: "My Documents"
    });
  } catch (error) {
    if (DEBUG) console.error("Error finding My Documents folder:", error.response?.data || error.message);
    res.status(500).json({ 
      error: "Failed to find My Documents folder",
      details: error.response?.data?.message || error.message 
    });
  }
});

// GET /api/workbook-copy-create/team-workspaces - Get team workspaces where the build user is a member
router.get("/team-workspaces", async (req, res) => {
  try {
    if (DEBUG) console.log("=== Fetching real team workspace folders ===");

    const headers = await getSigmaHeaders();
    const embedUserEmail = process.env.BUILD_EMAIL;
    const memberId = await lookupMemberId(embedUserEmail);
    
    // Get member files to see what folders the build user has access to
    const memberFilesUrl = `${process.env.BASE_URL}/members/${memberId}/files?typeFilters=folder&limit=500`;
    if (DEBUG) console.log(`Fetching member folders: ${memberFilesUrl}`);
    
    const memberFilesResponse = await axios.get(memberFilesUrl, { headers });
    const memberFolders = memberFilesResponse.data.entries || [];
    
    if (DEBUG) console.log(`Build user has access to ${memberFolders.length} folders`);
    if (DEBUG) {
      const folderDetails = memberFolders.map(f => ({ 
        name: f.name, 
        path: f.path, 
        id: f.id, 
        type: f.type,
        ownerId: f.ownerId
      }));
      console.log("Accessible folders:", JSON.stringify(folderDetails, null, 2));
    }
    
    // Look for team workspace folders (folders that are not "My Documents" and not owned by the build user)
    const teamWorkspaces = [];
    
    for (const folder of memberFolders) {
      if (folder.type !== "folder") continue;
      
      // Skip "My Documents" folders
      if (folder.name === "My Documents" || folder.path === "My Documents") continue;
      
      // Skip folders owned by the build user (these are personal folders)
      if (folder.ownerId === memberId) continue;
      
      // This is likely a team workspace folder
      teamWorkspaces.push({
        id: folder.id,
        name: folder.name,
        path: folder.path || folder.name,
        teamId: folder.id // Use folder ID as team identifier
      });
      
      if (DEBUG) console.log(`Found team workspace folder: ${folder.name} (${folder.id})`);
    }
    
    // If no team folders found, fall back to My Documents only approach
    if (teamWorkspaces.length === 0) {
      if (DEBUG) console.log("No team workspace folders found, user can only copy to My Documents");
    }
    
    if (DEBUG) console.log(`=== Final result: ${teamWorkspaces.length} real team workspaces ===`);
    if (DEBUG) console.log("Team workspaces:", JSON.stringify(teamWorkspaces, null, 2));

    res.json({ 
      teamWorkspaces: teamWorkspaces
    });
  } catch (error) {
    if (DEBUG) console.error("Error fetching team workspaces:", error.response?.data || error.message);
    res.status(500).json({ 
      error: "Failed to fetch team workspaces",
      details: error.response?.data?.message || error.message 
    });
  }
});

// GET /api/workbook-copy-create/folders - Get available folders for workbook placement
router.get("/folders", async (req, res) => {
  try {
    if (DEBUG) console.log("Fetching folders for workbook placement");

    const headers = await getSigmaHeaders();
    const response = await axios.get(`${process.env.BASE_URL}/files`, { headers });
    const data = response.data;

    // Filter for folders only and check for write permissions
    const allFolders = data.entries || [];
    const writableFolders = allFolders.filter(entry => {
      // Only include folders
      if (entry.type !== "folder") return false;
      
      // Check permissions - look for write capabilities
      // This may need adjustment based on actual permission structure from Sigma
      const permissions = entry.permissions || [];
      const hasWritePermission = permissions.some(permission => 
        permission.includes("write") || 
        permission.includes("create") || 
        permission.includes("edit") ||
        permission === "full" ||
        permission === "admin"
      );
      
      // If no permissions array is present, assume we have access (common for user's own folders)
      return permissions.length === 0 || hasWritePermission;
    });
    
    if (DEBUG) console.log(`Found ${writableFolders.length} writable folders out of ${allFolders.length} total folders`);

    res.json({ 
      folders: writableFolders.map(folder => ({
        id: folder.id,
        name: folder.name,
        path: folder.path || folder.name
      }))
    });
  } catch (error) {
    if (DEBUG) console.error("Error fetching folders:", error.response?.data || error.message);
    res.status(500).json({ 
      error: "Failed to fetch folders",
      details: error.response?.data?.message || error.message 
    });
  }
});

// POST /api/workbook-copy-create/copy - Copy a workbook
router.post("/copy", async (req, res) => {
  try {
    const { workbookId, destinationFolderId, name } = req.body;

    if (!workbookId) {
      return res.status(400).json({ error: "workbookId is required" });
    }

    const copyData = {};
    if (destinationFolderId) {
      copyData.destinationFolderId = destinationFolderId;
    } else {
      // If no destination folder specified, copy to build user's My Documents folder
      copyData.destinationFolderId = "rleTgkyUSzKwLRWNFK5tS"; // Build user's My Documents folder
    }
    
    // Handle name parameter - generate default if blank/undefined
    if (name && name.trim()) {
      copyData.name = name.trim();
    } else {
      // If no name provided, get the original workbook name and add "Copy" suffix
      try {
        const headers = await getSigmaHeaders();
        const workbookResponse = await axios.get(`${process.env.BASE_URL}/workbooks/${workbookId}`, { headers });
        const originalName = workbookResponse.data.name || "Workbook";
        copyData.name = `${originalName} (copy)`;
        if (DEBUG) console.log(`Generated default name for copy: ${copyData.name}`);
      } catch (nameError) {
        // Fallback if we can't get original name
        copyData.name = "Workbook Copy";
        if (DEBUG) console.log("Using fallback name for copy:", copyData.name);
      }
    }

    if (DEBUG) console.log("Copying workbook:", { workbookId, destinationFolderId, name });
    if (DEBUG) console.log("Request URL:", `${process.env.BASE_URL}/workbooks/${workbookId}/copy`);
    if (DEBUG) console.log("Request body:", JSON.stringify(copyData));

    const headers = await getSigmaHeaders();
    const response = await axios.post(`${process.env.BASE_URL}/workbooks/${workbookId}/copy`, copyData, { headers });
    const data = response.data;
    if (DEBUG) console.log("Workbook copied successfully:", data);

    res.json({
      success: true,
      workbook: data
    });
  } catch (error) {
    if (DEBUG) console.error("Error copying workbook:", error.response?.data || error.message);
    res.status(500).json({
      error: "Failed to copy workbook",
      details: error.response?.data?.message || error.message
    });
  }
});

// POST /api/workbook-copy-create/create - Create a new empty workbook
router.post("/create", async (req, res) => {
  try {
    const { name, folderId } = req.body;

    if (!name) {
      return res.status(400).json({ error: "name is required" });
    }

    const createData = { name };
    // Create workbooks in the build user's My Documents folder
    if (folderId) {
      createData.folderId = folderId;
    } else {
      // Use the verified build user's My Documents folder ID
      createData.folderId = "rleTgkyUSzKwLRWNFK5tS"; // Build user's My Documents folder
      if (DEBUG) console.log(`Creating workbook in build user's My Documents folder: ${createData.folderId}`);
    }

    if (DEBUG) console.log("Creating new workbook:", { name, folderId });
    if (DEBUG) console.log("Request URL:", `${process.env.BASE_URL}/workbooks`);
    if (DEBUG) console.log("Request body:", JSON.stringify(createData));

    const headers = await getSigmaHeaders();
    const response = await axios.post(`${process.env.BASE_URL}/workbooks`, createData, { headers });
    const data = response.data;
    if (DEBUG) console.log("Workbook created successfully:", data);

    res.json({
      success: true,
      workbook: data
    });
  } catch (error) {
    if (DEBUG) console.error("Error creating workbook:", error.response?.data || error.message);
    res.status(500).json({
      error: "Failed to create workbook",
      details: error.response?.data?.message || error.message
    });
  }
});

// GET /api/workbook-copy-create/workbook/:workbookId/folder - Get the folder ID of a specific workbook
router.get("/workbook/:workbookId/folder", async (req, res) => {
  try {
    const { workbookId } = req.params;

    if (DEBUG) console.log("Getting folder for workbook:", workbookId);

    const headers = await getSigmaHeaders();
    const response = await axios.get(`${process.env.BASE_URL}/workbooks/${workbookId}`, { headers });
    const workbook = response.data;
    const folderId = workbook.folderId || workbook.parentId;

    if (DEBUG) console.log("Workbook folder ID:", folderId);

    res.json({ 
      folderId,
      workbookName: workbook.name
    });
  } catch (error) {
    if (DEBUG) console.error("Error getting workbook folder:", error.response?.data || error.message);
    res.status(500).json({
      error: "Failed to get workbook folder",
      details: error.response?.data?.message || error.message
    });
  }
});

// GET /api/workbook-copy-create/all-workbooks - Get all workbooks accessible to the embed user
router.get("/all-workbooks", async (req, res) => {
  try {
    if (DEBUG) console.log("Fetching workbooks accessible to embed user via member-based filtering");

    const headers = await getSigmaHeaders();
    
    // Step 1: Get the memberId for the embed user
    const embedUserEmail = process.env.BUILD_EMAIL;
    const memberId = await lookupMemberId(embedUserEmail);
    if (DEBUG) console.log(`Found memberId for ${embedUserEmail}: ${memberId}`);

    // Step 2: Get all files accessible to this member (filtered by workbooks)
    const memberFilesUrl = `${process.env.BASE_URL}/members/${memberId}/files?typeFilters=workbook&limit=500`;
    if (DEBUG) console.log(`Fetching member files: ${memberFilesUrl}`);
    
    const memberFilesResponse = await axios.get(memberFilesUrl, { headers });
    const memberFiles = memberFilesResponse.data.entries || [];
    const memberFileIds = memberFiles.map(file => file.id);
    
    if (DEBUG) console.log(`Found ${memberFiles.length} files accessible to member`);

    // Step 3: Get all workbooks from the system
    const workbooksResponse = await axios.get(`${process.env.BASE_URL}/workbooks?limit=500`, { headers });
    const allWorkbooks = workbooksResponse.data.entries || [];
    
    // Step 4: Filter workbooks to only include those accessible to the member BUT EXCLUDE My Documents
    const accessibleWorkbooks = allWorkbooks.filter(workbook => {
      const isAccessible = memberFileIds.includes(workbook.workbookId);
      const path = workbook.path || "";
      const isMyDocuments = path === "My Documents" || path.includes("My Documents");
      
      // Include if accessible but NOT in My Documents (those go in the other dropdown)
      return isAccessible && !isMyDocuments;
    });
    
    if (DEBUG) console.log(`Found ${accessibleWorkbooks.length} non-My-Documents workbooks accessible to embed user out of ${allWorkbooks.length} total workbooks`);

    // Return in same format as regular workbooks endpoint
    const formattedWorkbooks = accessibleWorkbooks.map((w) => ({
      id: w.workbookId,
      urlId: w.workbookUrlId, 
      name: w.name,
      url: w.url,
      version: w.latestVersion,
      path: w.path,
      latestVersion: w.latestVersion,
    }));

    res.json({ workbooks: formattedWorkbooks });
  } catch (error) {
    if (DEBUG) console.error("Error fetching all workbooks:", error.response?.data || error.message);
    res.status(500).json({ 
      error: "Failed to fetch all workbooks",
      details: error.response?.data?.message || error.message 
    });
  }
});

// GET /api/workbook-copy-create/my-documents-workbooks - Get workbooks from embed user's My Documents folder
router.get("/my-documents-workbooks", async (req, res) => {
  try {
    if (DEBUG) console.log("Fetching embed user's My Documents workbooks via member-based filtering");

    const headers = await getSigmaHeaders();
    
    // Step 1: Get the memberId for the embed user
    const embedUserEmail = process.env.BUILD_EMAIL;
    const memberId = await lookupMemberId(embedUserEmail);
    if (DEBUG) console.log(`Found memberId for ${embedUserEmail}: ${memberId}`);

    // Step 2: Get all files accessible to this member (filtered by workbooks)
    const memberFilesUrl = `${process.env.BASE_URL}/members/${memberId}/files?typeFilters=workbook&limit=500`;
    if (DEBUG) console.log(`Fetching member files: ${memberFilesUrl}`);
    
    const memberFilesResponse = await axios.get(memberFilesUrl, { headers });
    const memberFiles = memberFilesResponse.data.entries || [];
    const memberFileIds = memberFiles.map(file => file.id);
    
    if (DEBUG) console.log(`Found ${memberFiles.length} files accessible to member for My Documents filtering`);

    // Step 3: Get all workbooks from the system
    const workbooksResponse = await axios.get(`${process.env.BASE_URL}/workbooks?limit=500`, { headers });
    const allWorkbooks = workbooksResponse.data.entries || [];
    
    if (DEBUG) {
      const myDocsWorkbooks = allWorkbooks.filter(wb => {
        const path = wb.path || "";
        return path === "My Documents" || path.includes("My Documents");
      });
      console.log(`Total workbooks in system: ${allWorkbooks.length}`);
      console.log(`Total My Documents workbooks in system: ${myDocsWorkbooks.length}`);
      if (myDocsWorkbooks.length > 0) {
        console.log("My Documents workbooks found:", myDocsWorkbooks.map(wb => ({
          name: wb.name,
          id: wb.workbookId,
          path: wb.path,
          ownerId: wb.ownerId
        })));
      }
      console.log(`Member ${embedUserEmail} has access to ${memberFileIds.length} files:`, memberFileIds.slice(0, 10));
    }
    
    // Step 4: Filter workbooks to only include those accessible to the member AND in My Documents folder
    const myDocumentsWorkbooks = allWorkbooks.filter(workbook => {
      const isAccessible = memberFileIds.includes(workbook.workbookId);
      const path = workbook.path || "";
      const isMyDocuments = path === "My Documents" || path.includes("My Documents");
      
      if (DEBUG && isAccessible) {
        console.log(`Workbook "${workbook.name}" - path: "${path}" - isMyDocuments: ${isMyDocuments} - workbookId: ${workbook.workbookId}`);
      }
      
      // Additional debug: show all workbooks that match the criteria
      if (DEBUG && isMyDocuments) {
        console.log(`POTENTIAL My Documents workbook: "${workbook.name}" - accessible: ${isAccessible} - path: "${path}"`);
      }
      
      return isAccessible && isMyDocuments;
    });
    
    if (DEBUG) console.log(`Found ${myDocumentsWorkbooks.length} My Documents workbooks accessible to embed user`);

    // Return in same format as regular workbooks endpoint
    const formattedWorkbooks = myDocumentsWorkbooks.map((w) => ({
      id: w.workbookId,
      urlId: w.workbookUrlId, 
      name: w.name,
      url: w.url,
      version: w.latestVersion,
      path: w.path,
      latestVersion: w.latestVersion,
    }));

    res.json({ workbooks: formattedWorkbooks });
  } catch (error) {
    if (DEBUG) console.error("Error fetching My Documents workbooks:", error.response?.data || error.message);
    res.status(500).json({ 
      error: "Failed to fetch My Documents workbooks",
      details: error.response?.data?.message || error.message 
    });
  }
});

module.exports = router;