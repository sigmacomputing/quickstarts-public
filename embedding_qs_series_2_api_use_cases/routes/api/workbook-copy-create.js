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

// Helper function to check if a workbook name exists in a specific folder and generate unique name
async function generateUniqueWorkbookName(baseName, destinationFolderId) {
  try {
    const headers = await getSigmaHeaders();
    
    // Get all workbooks in the system to check for name conflicts
    const workbooksResponse = await axios.get(`${process.env.BASE_URL}/workbooks?limit=500`, { headers });
    const allWorkbooks = workbooksResponse.data.entries || [];
    
    // Filter workbooks that are in the same destination folder
    const workbooksInFolder = allWorkbooks.filter(wb => {
      // For My Documents folder, check path
      if (destinationFolderId === "rleTgkyUSzKwLRWNFK5tS") {
        const path = wb.path || "";
        return path === "My Documents" || path.includes("My Documents");
      }
      // For other folders, check folderId (if available in API response)
      return wb.folderId === destinationFolderId || wb.parentId === destinationFolderId;
    });
    
    if (DEBUG) {
      console.log(`Checking for name conflicts in folder ${destinationFolderId}`);
      console.log(`Found ${workbooksInFolder.length} existing workbooks in target folder`);
      if (workbooksInFolder.length > 0) {
        console.log("Existing workbook names:", workbooksInFolder.map(wb => wb.name));
      }
    }
    
    // Check if the base name already exists
    const existingNames = workbooksInFolder.map(wb => wb.name.toLowerCase());
    
    let finalName = baseName;
    let counter = 1;
    
    // Keep incrementing until we find a unique name
    while (existingNames.includes(finalName.toLowerCase())) {
      finalName = `${baseName} (${counter})`;
      counter++;
      
      if (DEBUG) console.log(`Name conflict detected, trying: ${finalName}`);
      
      // Safety check to prevent infinite loops
      if (counter > 100) {
        finalName = `${baseName} (${Date.now()})`;
        break;
      }
    }
    
    if (DEBUG && finalName !== baseName) {
      console.log(`Generated unique name: ${finalName} (original: ${baseName})`);
    }
    
    return finalName;
  } catch (error) {
    if (DEBUG) console.error("Error checking for duplicate names:", error.message);
    // If we can't check for duplicates, just return the base name
    return baseName;
  }
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
    if (DEBUG) console.log("=== Fetching teams where build user is a member ===");

    const headers = await getSigmaHeaders();
    const embedUserEmail = process.env.BUILD_EMAIL;
    const memberId = await lookupMemberId(embedUserEmail);
    
    // Step 1: Get all teams and try multiple approaches to detect membership
    const teamsUrl = `${process.env.BASE_URL}/teams`;
    if (DEBUG) console.log(`Fetching all teams: ${teamsUrl}`);
    
    const teamsResponse = await axios.get(teamsUrl, { headers });
    const allTeams = teamsResponse.data.entries || [];
    
    if (DEBUG) console.log(`Found ${allTeams.length} total teams in the system`);
    
    // Step 2: Try to detect team membership through multiple approaches
    const userTeams = [];
    
    // Approach 1: Check team membership via teams API
    for (const team of allTeams) {
      try {
        const teamMembersUrl = `${process.env.BASE_URL}/teams/${team.teamId}/members`;
        const teamMembersResponse = await axios.get(teamMembersUrl, { headers });
        const teamMembers = teamMembersResponse.data.entries || [];
        
        const isMember = teamMembers.some(member => member.memberId === memberId);
        
        if (isMember) {
          userTeams.push(team);
          if (DEBUG) console.log(`✓ Found via teams API: ${team.name} (${team.teamId})`);
        }
      } catch (teamError) {
        if (DEBUG) console.log(`Could not check membership for team ${team.name}: ${teamError.message}`);
      }
    }
    
    // Approach 2: If no teams found via API, infer from member's accessible files
    if (userTeams.length === 0) {
      if (DEBUG) console.log("No teams found via teams API, trying to infer from member's accessible files");
      
      try {
        const memberFilesUrl = `${process.env.BASE_URL}/members/${memberId}/files?limit=500`;
        const memberFilesResponse = await axios.get(memberFilesUrl, { headers });
        const memberFiles = memberFilesResponse.data.entries || [];
        
        // Look at workbook paths to infer team membership
        const workbooks = memberFiles.filter(f => f.type === 'workbook');
        const teamPaths = new Set();
        
        workbooks.forEach(wb => {
          if (wb.path && wb.path !== 'My Documents') {
            teamPaths.add(wb.path);
          }
        });
        
        if (DEBUG) console.log(`Found workbook paths that suggest team access:`, Array.from(teamPaths));
        
        // For each path that looks like a team, try to find the corresponding team
        for (const path of teamPaths) {
          const matchingTeam = allTeams.find(team => 
            team.name.toLowerCase() === path.toLowerCase() ||
            team.name.toLowerCase().replace(/_/g, ' ') === path.toLowerCase() ||
            path.toLowerCase().includes(team.name.toLowerCase()) ||
            team.name.toLowerCase().includes(path.toLowerCase())
          );
          
          if (matchingTeam && !userTeams.find(t => t.teamId === matchingTeam.teamId)) {
            userTeams.push(matchingTeam);
            if (DEBUG) console.log(`✓ Inferred team membership from workbook path "${path}": ${matchingTeam.name}`);
          }
        }
      } catch (memberFilesError) {
        if (DEBUG) console.log(`Error accessing member files: ${memberFilesError.message}`);
      }
    }
    
    if (DEBUG) console.log(`Build user appears to be member of ${userTeams.length} teams`);
    
    // Step 3: For each detected team, try to find their workspace folder
    const teamWorkspaces = [];
    
    // Get all folders to search for team workspace folders
    const allFilesResponse = await axios.get(`${process.env.BASE_URL}/files`, { headers });
    const allFiles = allFilesResponse.data.entries || [];
    const allFolders = allFiles.filter(file => file.type === "folder");
    
    if (DEBUG) console.log(`Searching through ${allFolders.length} folders for team workspace folders`);
    
    // Also get member's accessible files to see what folders they can access
    let memberAccessibleFolders = [];
    try {
      const memberFilesUrl = `${process.env.BASE_URL}/members/${memberId}/files?typeFilters=folder&limit=500`;
      const memberFilesResponse = await axios.get(memberFilesUrl, { headers });
      memberAccessibleFolders = memberFilesResponse.data.entries || [];
      if (DEBUG) console.log(`Member has access to ${memberAccessibleFolders.length} folders`);
    } catch (memberError) {
      if (DEBUG) console.log(`Could not get member's accessible folders: ${memberError.message}`);
    }
    
    for (const team of userTeams) {
      if (DEBUG) console.log(`Looking for workspace folder for team "${team.name}"`);
      
      // Look for folders that match this team name in both all folders and member's accessible folders
      const searchSources = [
        { name: 'system folders', folders: allFolders },
        { name: 'member accessible folders', folders: memberAccessibleFolders }
      ];
      
      let teamFolder = null;
      
      for (const source of searchSources) {
        const teamFolders = source.folders.filter(folder => {
          const folderName = folder.name.toLowerCase();
          const teamName = team.name.toLowerCase();
          
          return (
            folderName === teamName ||
            folderName.includes(teamName) ||
            teamName.includes(folderName) ||
            folder.path?.toLowerCase().includes(teamName) ||
            // Additional matching for common variations
            folderName.replace(/_/g, ' ') === teamName.replace(/_/g, ' ') ||
            folderName.replace(/\s+/g, '_') === teamName.replace(/\s+/g, '_')
          );
        });
        
        if (DEBUG && teamFolders.length > 0) {
          console.log(`Found ${teamFolders.length} potential folders in ${source.name}:`, teamFolders.map(f => f.name));
        }
        
        if (teamFolders.length > 0) {
          teamFolder = teamFolders[0];
          if (DEBUG) console.log(`Using folder from ${source.name}: ${teamFolder.name} (${teamFolder.id})`);
          break;
        }
      }
      
      if (teamFolder) {
        teamWorkspaces.push({
          id: teamFolder.id,
          name: team.name,
          path: teamFolder.path || teamFolder.name,
          teamId: team.teamId,
          teamName: team.name
        });
        
        if (DEBUG) console.log(`✓ Added real workspace for team ${team.name}: ${teamFolder.name} (${teamFolder.id})`);
      } else {
        // Try to find workspace folder by looking for workbooks in team-named paths
        try {
          const memberFilesUrl = `${process.env.BASE_URL}/members/${memberId}/files?typeFilters=workbook&limit=500`;
          const memberFilesResponse = await axios.get(memberFilesUrl, { headers });
          const memberWorkbooks = memberFilesResponse.data.entries || [];
          
          // Check if there are workbooks with this team's path
          const teamWorkbooks = memberWorkbooks.filter(wb => 
            wb.path && (
              wb.path.toLowerCase() === team.name.toLowerCase() ||
              wb.path.toLowerCase().includes(team.name.toLowerCase())
            )
          );
          
          if (teamWorkbooks.length > 0) {
            // If user has workbooks in this team path, assume the team workspace exists
            // even if we can't find the folder directly
            if (DEBUG) console.log(`Found ${teamWorkbooks.length} workbooks in team path "${team.name}" - assuming team workspace exists`);
            
            // For now, we'll use a synthetic folder ID but indicate it's for the team workspace
            teamWorkspaces.push({
              id: `team-workspace-${team.teamId}`, // Synthetic ID to indicate team workspace
              name: team.name,
              path: team.name,
              teamId: team.teamId,
              teamName: team.name,
              isTeamWorkspace: true // Flag to indicate this is a team workspace
            });
            
            if (DEBUG) console.log(`✓ Added inferred team workspace for ${team.name} based on workbook paths`);
          } else {
            // No evidence of team workspace, fall back to My Documents
            if (DEBUG) console.log(`No evidence of workspace folder for team ${team.name}, using My Documents fallback`);
            
            teamWorkspaces.push({
              id: "rleTgkyUSzKwLRWNFK5tS", // My Documents folder as fallback
              name: `${team.name} (via My Documents)`,
              path: team.name,
              teamId: team.teamId,
              teamName: team.name
            });
          }
        } catch (workbookError) {
          if (DEBUG) console.log(`Error checking workbooks for team ${team.name}: ${workbookError.message}`);
          
          // Final fallback
          teamWorkspaces.push({
            id: "rleTgkyUSzKwLRWNFK5tS",
            name: `${team.name} (via My Documents)`,
            path: team.name,
            teamId: team.teamId,
            teamName: team.name
          });
        }
      }
    }
    
    if (DEBUG) console.log(`=== Final result: ${teamWorkspaces.length} team workspaces ===`);
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
    
    // Handle destination folder ID
    if (destinationFolderId) {
      // Check if this is a synthetic team workspace ID
      if (destinationFolderId.startsWith('team-workspace-')) {
        if (DEBUG) console.log(`Detected synthetic team workspace ID: ${destinationFolderId}`);
        
        // Based on testing, team workspaces in Sigma don't work like traditional folders
        // We'll copy to My Documents and then share with the team to provide similar functionality
        const teamId = destinationFolderId.replace('team-workspace-', '');
        
        if (DEBUG) console.log(`Team workspace copy requested for team: ${teamId}`);
        if (DEBUG) console.log(`Copying to My Documents and will share with team after copy`);
        
        // Copy to My Documents first
        copyData.destinationFolderId = "rleTgkyUSzKwLRWNFK5tS";
        
        // Store team ID for post-copy sharing
        copyData._teamIdForSharing = teamId;
        
      } else {
        // Regular folder ID
        copyData.destinationFolderId = destinationFolderId;
      }
    } else {
      // If no destination folder specified, copy to build user's My Documents folder
      copyData.destinationFolderId = "rleTgkyUSzKwLRWNFK5tS"; // Build user's My Documents folder
    }
    
    // Handle name parameter - generate default if blank/undefined
    let proposedName;
    if (name && name.trim()) {
      proposedName = name.trim();
    } else {
      // If no name provided, get the original workbook name and add "Copy" suffix
      try {
        const headers = await getSigmaHeaders();
        const workbookResponse = await axios.get(`${process.env.BASE_URL}/workbooks/${workbookId}`, { headers });
        const originalName = workbookResponse.data.name || "Workbook";
        proposedName = `${originalName} (copy)`;
        if (DEBUG) console.log(`Generated default name for copy: ${proposedName}`);
      } catch (nameError) {
        // Fallback if we can't get original name
        proposedName = "Workbook Copy";
        if (DEBUG) console.log("Using fallback name for copy:", proposedName);
      }
    }
    
    // Check for duplicate names and generate unique name if needed
    copyData.name = await generateUniqueWorkbookName(proposedName, copyData.destinationFolderId);
    if (DEBUG && copyData.name !== proposedName) {
      console.log(`Name changed due to conflict: ${proposedName} -> ${copyData.name}`);
    }

    if (DEBUG) console.log("Copying workbook (NEW VERSION):", { workbookId, destinationFolderId, name });
    if (DEBUG) console.log("Request URL:", `${process.env.BASE_URL}/workbooks/${workbookId}/copy`);
    if (DEBUG) console.log("Request body:", JSON.stringify(copyData));

    // Store team ID for post-copy sharing before removing it from copyData
    const teamIdForSharing = copyData._teamIdForSharing;
    delete copyData._teamIdForSharing; // Remove from copy request

    const headers = await getSigmaHeaders();
    const response = await axios.post(`${process.env.BASE_URL}/workbooks/${workbookId}/copy`, copyData, { headers });
    const data = response.data;
    if (DEBUG) console.log("Workbook copied successfully:", data);

    // If this was a team workspace copy, share the workbook with the team
    if (teamIdForSharing) {
      if (DEBUG) console.log(`Sharing copied workbook with team: ${teamIdForSharing}`);
      
      try {
        const grantsUrl = `${process.env.BASE_URL}/workbooks/${data.workbookId}/grants`;
        const grantsData = {
          grants: [
            {
              grantee: {
                teamId: teamIdForSharing
              },
              permission: 'view'
            }
          ]
        };
        
        await axios.post(grantsUrl, grantsData, { headers });
        if (DEBUG) console.log("Successfully shared workbook with team");
        
        // Add a note to the response that it was shared with the team
        data._sharedWithTeam = teamIdForSharing;
        
      } catch (shareError) {
        if (DEBUG) console.error("Failed to share workbook with team:", shareError.response?.data || shareError.message);
        // Don't fail the entire operation if sharing fails
        data._shareError = "Failed to automatically share with team workspace";
      }
    }

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

    // Determine destination folder
    const destinationFolderId = folderId || "rleTgkyUSzKwLRWNFK5tS"; // Build user's My Documents folder
    if (DEBUG) console.log(`Creating workbook in build user's My Documents folder: ${destinationFolderId}`);
    
    // Check for duplicate names and generate unique name if needed
    const uniqueName = await generateUniqueWorkbookName(name, destinationFolderId);
    if (DEBUG && uniqueName !== name) {
      console.log(`Name changed due to conflict: ${name} -> ${uniqueName}`);
    }
    
    const createData = { 
      name: uniqueName,
      folderId: destinationFolderId
    };

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
    // Get user email from query parameter, default to build user for backwards compatibility
    const embedUserEmail = req.query.userEmail || process.env.BUILD_EMAIL;
    if (DEBUG) console.log(`Fetching workbooks accessible to embed user: ${embedUserEmail}`);

    const headers = await getSigmaHeaders();
    
    // Step 1: Get the memberId for the embed user
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
    
    // Step 4: Filter workbooks to only include those accessible to the member
    const accessibleWorkbooks = allWorkbooks.filter(workbook => {
      const isAccessible = memberFileIds.includes(workbook.workbookId);
      return isAccessible;
    });
    
    if (DEBUG) console.log(`Found ${accessibleWorkbooks.length} workbooks accessible to embed user out of ${allWorkbooks.length} total workbooks`);

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
    
    // Add refresh parameter to force cache bypass if specified
    const shouldRefresh = req.query.refresh === 'true';
    if (shouldRefresh && DEBUG) {
      console.log("Refresh requested - bypassing any potential caches");
    }

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