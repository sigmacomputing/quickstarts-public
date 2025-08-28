# Get Member Details

## API Endpoints Used

- `GET /v2/members?search={email}` → [List Members](https://help.sigmacomputing.com/reference/listmembers)
- `GET /v2/members/{memberId}` → [Get Member](https://help.sigmacomputing.com/reference/getmember)

## Expected Output

- Detailed member information including profile, permissions, and team memberships
- Account type, status, creation date, and last login information
- Associated team and workspace permissions

## Use Cases

- Look up specific user account details
- Audit individual user permissions
- Troubleshoot user access issues
- Verify user account configuration

## Important Notes

- Can search by either EMAIL or MEMBERID environment variable
- If using email, the @ character is automatically URL-encoded
- Returns complete user profile and permission details