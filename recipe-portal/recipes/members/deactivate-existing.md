# Deactivate Existing Member

## API Endpoints Used

- `DELETE /v2/members/{memberId}` → [Deactivate Member](https://help.sigmacomputing.com/reference/deletemember)

## Expected Output

- Confirmation of member deactivation
- Final member status showing account as inactive
- Cleanup confirmation for associated permissions

## Use Cases

- Remove users who have left the organization
- Deactivate accounts for security compliance
- Clean up unused or test accounts
- Manage user lifecycle for offboarding

## Important Notes

- ⚠️ This performs a soft delete (deactivation), not permanent removal
- Deactivated users cannot access Sigma but their data remains
- Action cannot be easily reversed - contact support for reactivation