# Create Connection Permission

## API Endpoints Used

- `POST /v2/connections/{connectionId}/grants` → [Create Connection Grant](https://help.sigmacomputing.com/reference/createconnectiongrant)

## Expected Output

- Confirmation of connection permission grant
- Permission details including access level and connection information
- Member and connection summary

## Use Cases

- Grant data source access to specific users
- Control who can use particular database connections
- Manage data security and access governance
- Set up connection-level permissions for compliance

## Important Notes

- Requires valid MEMBERID and CONNECTIONID in environment variables
- Connection grants control access to underlying data sources
- Essential for data governance and security compliance