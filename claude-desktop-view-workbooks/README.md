# Claude Desktop: View Live Sigma Workbooks

A local MCP server that lets Claude Desktop find a Sigma workbook by name and show it live and interactive. It is a learning and prototyping pattern: it runs on your machine with credentials in a local `.env` file.

It exposes two tools and one view:

| Name | Purpose |
| --- | --- |
| `search_workbooks` | Fuzzy search of workbook names. Returns the name, slug, URL, path and last-updated date. |
| `show_sigma_workbook` | Opens a workbook from its slug or URL using a freshly signed, single-use JWT. |
| `ui://sigma-workbooks/workbook-view` | A small MCP Apps view that shows the workbook inline when the host supports it. Otherwise Claude is told to open the URL in its browser pane. |

## Setup

1. Install Node.js 18 or later.
2. Install the dependencies:

   ```
   npm install
   ```

3. Copy `.env.example` to `.env` and fill in your values. See the comments in the file.
4. Run the tests (no Sigma credentials needed):

   ```
   npm test
   ```

5. Add the server to Claude Desktop's `claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`), using the full path to `server.js`:

   ```json
   {
     "mcpServers": {
       "sigma-workbooks": {
         "command": "node",
         "args": ["/full/path/to/claude-desktop-view-workbooks/server.js"]
       }
     }
   }
   ```

6. Restart Claude Desktop, then ask for a workbook by name.

## Notes

- Each signed link works once. If a workbook fails to load with "The JWT has already been used", ask Claude to open it again for a new link.
- Search and view both run as the default embed user (`EMAIL` in `.env`), so results match what that user can open.
- The server writes only to stderr. Anything written to stdout would break the connection to Claude Desktop.
- Pass the workbook slug or URL, never Sigma's internal workbook ID.
