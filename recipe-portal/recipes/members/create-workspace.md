# Create Workspace

## API Endpoints Used

- `POST /v2/workspaces` → [Create Workspace](https://help.sigmacomputing.com/reference/createworkspace)

## Expected Output

- Confirmation of new workspace creation
- Workspace details including workspaceId and name
- Owner assignment confirmation

## Use Cases

- Create dedicated workspaces for new projects or teams
- Organize content by department or use case
- Set up isolated environments for different user groups
- Establish workspace structure for new organizations

## Important Notes

- Workspace name is automatically generated using the MEMBERID
- Creating user becomes the initial workspace owner
- Workspace provides isolated content organization