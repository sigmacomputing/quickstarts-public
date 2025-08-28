# Sync Schema

## API Endpoints Used

- `POST /v2/connections/{connectionId}/lookup` → [Lookup Connection Path](https://help.sigmacomputing.com/reference/lookupconnectionpath)
- `GET /v2/files` → [List Files](https://help.sigmacomputing.com/reference/listfiles)
- `POST /v2/connections/{connectionId}/sync` → [Sync Connection](https://help.sigmacomputing.com/reference/syncconnection)

## Expected Output

- Console log showing schema lookup results
- List of tables found within the specified schema
- Sync status for each table processed
- Success/failure confirmation for each table sync operation

## Use Cases

- Automatically sync new tables added to your data warehouse
- Refresh schema after structural changes in Snowflake
- Bulk synchronization of multiple tables in a schema
- Maintain up-to-date data source metadata

## Important Notes

- SYNC_PATH must be a valid JSON array representing the schema path
- Process can take time depending on number of tables and schema complexity
- Each table is synced individually with status reporting