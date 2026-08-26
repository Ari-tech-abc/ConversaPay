# Talk2Pay brand compatibility plan

Talk2Pay is the official public-facing product and project name. The existing `conversapay.org` domain remains active for infrastructure compatibility.

Legacy `conversapay` identifiers remain temporarily only in filenames, storage keys, API identifiers, DOM IDs, and deployment paths where changing them would break existing clients. They are technical compatibility identifiers, not the displayed product brand.

## Migration rules

- Public copy, titles, metadata, email templates, WordPress labels, generated sites, logs, and UI accessibility labels use Talk2Pay.
- Keep old API keys, local-storage keys, database columns, webhook identifiers, and domain paths readable during the deprecation window.
- Do not rename database columns or webhook identifiers without a migration and rollback plan.
- Add Talk2Pay aliases before removing legacy technical names.
- Track remaining legacy identifiers with a repository search before each release.
