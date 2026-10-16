# Activity and audit log growth (YT-18)

The activity log and security log keep one row per meaningful action. Bulk imports or thousands of trip creations in one day will grow the journal on disk. This is expected.

For long-running offices:

- Use the built-in backup schedule and verify restore on a clean PC periodically.
- Plan occasional archive export (`report.full`) before purging very old activity, if the owner accepts a separate retention policy.

No automatic purge runs in the pilot build; growth is documented so support can quote retention work separately.
