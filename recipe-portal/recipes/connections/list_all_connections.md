# List All Connections

## API Endpoints Used

- `GET /v2/connections` → [List Connections](https://help.sigmacomputing.com/reference/listconnections)

## Expected Output
JSON array of all connections in alphabetical order by name
Each connection includes: connectionId, name, type, status, and other metadata
Console log showing total count of connections

## Use Cases

- Audit all data connections in your organization
- Get connection IDs for other automation scripts
- Monitor connection health and status
- Generate reports of available data sources

## Important Notes

- Results are automatically sorted alphabetically by connection name
- Includes all connection types (databases, warehouses, cloud storage, etc.)