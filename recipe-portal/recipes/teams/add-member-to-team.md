# Add Member to Team

## API Endpoints Used

- `PATCH /v2/teams/{teamId}/members` → [Update Team Members](https://help.sigmacomputing.com/reference/updateteammembers)

## Expected Output

- Confirmation of successful team member addition
- Updated team membership details
- Member and team information summary

## Use Cases

- Assign new employees to appropriate teams
- Move users between teams during reorganization
- Grant team-based access to specific projects
- Manage team-based permissions and workflows

## Important Notes

- Requires valid MEMBERID and TEAMID in environment variables
- Member must be an active user in the organization
- Team membership affects access to team-specific resources