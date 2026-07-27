# Talk2Pay Rebrand Compatibility Plan

Public-facing product copy is Talk2Pay. Legacy `conversapay` identifiers remain temporarily in filenames, storage keys, API identifiers, and deployment paths where changing them would break existing clients.

## Migration rules

- Add new Talk2Pay aliases before removing legacy names.
- Keep old API keys and local-storage keys readable during a deprecation window.
- Do not rename database columns or webhook identifiers without a migration and rollback plan.
- Update logos, metadata, email templates, legal copy, WordPress labels, and generated site-builder copy together.
- Track remaining legacy identifiers with a repository search before each release.
