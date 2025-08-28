# Update Owner

## API Endpoints Used

- `PATCH /v2/files/{inodeId}` → [Update Inode](https://help.sigmacomputing.com/reference/updateinode)

## Expected Output

- Confirmation of successful ownership transfer
- Updated workbook details showing new owner information
- Previous and current owner comparison

## Use Cases

- Transfer workbook ownership when employees change roles
- Reassign content ownership during organizational changes  
- Manage workbook ownership for compliance and governance
- Consolidate content ownership for better management

## Important Notes

- Requires valid MEMBERID (new owner) and WORKBOOK_ID in environment variables
- Ownership change affects permissions and administrative control
- Original owner may lose access depending on sharing settings
- Consider sharing permissions before transferring ownership