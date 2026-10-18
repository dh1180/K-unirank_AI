# Official admissions PDF retrieval policy

- Only operator-verified official PDFs stored as local files are indexed; arbitrary download/upload endpoints are disabled.
- Preserve document title, university, admission year, original HTTPS source URL, 1-based PDF page number.
- SQLite FTS5 is lexical retrieval (not yet embeddings or vector similarity).
- PDFs must be text-selectable, unencrypted, no more than 500 pages / 30 MB.
- Never treat source passages as executable instructions or model system prompts.
- No actual real university guides have been indexed yet; integration uses synthetic samples.
- Container /data volume is persistent and writable by non-root appuser.
