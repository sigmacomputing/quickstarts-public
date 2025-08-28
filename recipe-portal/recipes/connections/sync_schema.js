// Title: Sync Schema
// Description: This script automates the synchronization of tables within a specified schema (Snowflake).

// Required Environment Variables:
// - CONNECTIONID: The ID of the connection to sync (available from connections list)
// - SYNC_PATH: JSON array representing the database path to sync
//   Examples:
//   - Schema sync: ["SAMPLE_DATABASE", "PUBLIC"] 
//   - Database sync: ["SAMPLE_DATABASE"]
//   - Table sync: ["SAMPLE_DATABASE", "PUBLIC", "TABLE_NAME"]
//
// Note: This script will discover and sync ALL tables within the specified path.
// For schema-level sync, it will sync all tables in that schema.

// Load environment variables from a specific .env file for configuration
require('dotenv').config({ path: 'recipes/.env' });

console.log('Environment Variables:', {
    baseURL: process.env.baseURL,
    CONNECTIONID: process.env.CONNECTIONID,
    SYNC_PATH: process.env.SYNC_PATH,
});

// Import the function to obtain a bearer token from the authenticate-bearer module
const getBearerToken = require('../get-access-token');

// Import Axios for making HTTP requests
const axios = require('axios');

// Load use-case specific variables from environment variables
const baseURL = process.env.baseURL; // Your base URL
const connectionId = process.env.CONNECTIONID; // Connection ID
let syncPaths;
let bearerToken; // Global variable to store the fetched bearer token

// Validate and parse SYNC_PATH
try {
    if (!process.env.SYNC_PATH) {
        throw new Error('SYNC_PATH is not defined in the .env file.');
    }

    // Parse SYNC_PATH as JSON
    syncPaths = JSON.parse(process.env.SYNC_PATH);

    if (!Array.isArray(syncPaths)) {
        throw new Error('SYNC_PATH must be a JSON array.');
    }
} catch (error) {
    console.error('Error parsing SYNC_PATH:', error.message);
    process.exit(1);
}

// Function to initialize the bearer token
async function initializeBearerToken() {
    bearerToken = await getBearerToken();
    if (!bearerToken) {
        console.error('Failed to obtain Bearer token.');
        process.exit(1);
    }
    console.log('Bearer token initialized successfully.');
}

// Function to resolve the `inodeId` for a schema/folder
async function lookupInodeId(path) {
    const endpoint = `${baseURL}/connection/${connectionId}/lookup`;
    console.log(`Looking up inodeId for path: ${JSON.stringify(path)} at URL: ${endpoint}`);

    try {
        const response = await axios.post(endpoint, { path }, {
            headers: { 'Authorization': `Bearer ${bearerToken}`, 'Content-Type': 'application/json' },
        });

        const { inodeId, kind } = response.data;
        if (!inodeId || !kind) {
            console.error(`Unexpected response: ${JSON.stringify(response.data)}`);
            return null;
        }

        console.log(`Resolved inodeId: ${inodeId} (kind: ${kind}) for path: ${JSON.stringify(path)}`);
        return { inodeId, kind };
    } catch (error) {
        console.error('Error resolving inodeId:', error.message);
        if (error.response) {
            console.error('Response Data:', error.response.data);
        }
        return null;
    }
}

// Function to list tables under a given inodeId
async function listTables(parentInodeId) {
    const endpoint = `${baseURL}/files?typeFilters=table&parentId=${parentInodeId}`;
    console.log(`Fetching tables for parentInodeId: ${parentInodeId} at URL: ${endpoint}`);

    try {
        const response = await axios.get(endpoint, {
            headers: { 'Authorization': `Bearer ${bearerToken}`, 'Accept': 'application/json' },
        });

        const tables = response.data.entries || [];
        console.log(`Found ${tables.length} tables under inodeId: ${parentInodeId}`);
        tables.forEach((table) => {
            console.log(`Table Name: ${table.name}, Table ID: ${table.id}`);
        });

        return tables.map((table) => ({
            id: table.id,
            name: table.name, // Include table name for path construction
        }));
    } catch (error) {
        console.error(`Error listing tables for inodeId: ${parentInodeId}`, error.message);
        if (error.response) {
            console.error('Response Data:', error.response.data);
        }
        return [];
    }
}

// Function to sync a specific table using its inodeId and full path
async function syncTable(inodeId, fullPath) {
    const endpoint = `${baseURL}/connections/${connectionId}/sync`;

    const payload = {
        path: fullPath, // Send the full path including the table name
    };

    try {
        console.log(`Starting sync for table with path: ${JSON.stringify(fullPath)}`);
        const response = await axios.post(endpoint, payload, {
            headers: { 'Authorization': `Bearer ${bearerToken}`, 'Content-Type': 'application/json' },
        });

        console.log(`Sync completed for table with path: ${JSON.stringify(fullPath)}`);
        console.log('Response:', response.data);
    } catch (error) {
        console.error(`Error syncing table with inodeId: ${inodeId}`, error.message);
        if (error.response) {
            console.error('Response Data:', error.response.data);
        }
    }
}

// Main function to list and sync tables
async function syncAllTables() {
    console.log(`Starting sync for path: ${JSON.stringify(syncPaths)}`);

    // Step 1: Resolve inodeId for the sync path
    const { inodeId } = await lookupInodeId(syncPaths);
    if (!inodeId) {
        console.error('Failed to resolve inodeId for path.');
        return;
    }

    // Step 2: List tables under the resolved inodeId
    const tables = await listTables(inodeId);
    if (tables.length === 0) {
        console.log('No tables found to sync.');
        return;
    }

    console.log(`Found ${tables.length} tables to sync.`);

    // Step 3: Sync each table
    for (const table of tables) {
        const fullPath = [...syncPaths, table.name]; // Append table name to sync path
        await syncTable(table.id, fullPath);
    }
}

// Execute the function if this script is run directly
if (require.main === module) {
    (async () => {
        await initializeBearerToken(); // Fetch the bearer token once
        await syncAllTables();
    })();
}
