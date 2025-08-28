# Create Workspace Permission

## API Endpoints Used

- `POST /v2/workspaces/{workspaceId}/grants` → [Create Workspace Grant](https://help.sigmacomputing.com/reference/createworkspacegrant)

## Expected Output

- Confirmation of permission grant creation
- Permission details including access level and scope
- Member and workspace information summary

## Use Cases

- Grant workspace access to specific users or teams
- Set up user/team permissions for project collaboration
- Manage workspace-level security and access control
- Establish content sharing permissions with different access levels

## Important Notes

- **Grantee Options**: Provide either MEMBERID (for individual users) or TEAMID (for teams) - not both
- **Permission Levels**: 
  - `view` - Read-only access to workspace content
  - `edit` - Can modify and create content in workspace  
  - `admin` - Full administrative access including user management
- **Required Parameters**: WORKSPACEID and PERMISSION must be specified
- Workspace grants control access to all content within the workspace