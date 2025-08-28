# Bulk Deactivate

## API Endpoints Used

- `GET /v2/members` → [List Members](https://help.sigmacomputing.com/reference/listmembers)
- `DELETE /v2/members/{memberId}` → [Deactivate Member](https://help.sigmacomputing.com/reference/deletemember)

## Expected Output

- List of users matching the specified name pattern
- Deactivation status for each matched user
- Summary of total users processed and deactivated

## Use Cases

- Remove multiple test accounts with similar naming patterns
- Bulk deactivate users from specific departments
- Clean up accounts based on naming conventions
- Automated user lifecycle management

## Important Notes

- ⚠️ Uses pattern matching - review matches carefully before proceeding
- Performs soft deletion (deactivation) - users cannot access but data remains
- Set DRY_RUN=true for preview mode to see matches without actually deactivating users