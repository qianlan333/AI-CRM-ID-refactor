# Media Library Variants Implementation

This implementation follows the mature image delivery pattern: keep the original image, generate multiple fixed-purpose variants, serve them through cacheable URLs, and let the frontend use responsive/lazy image loading.

Rules recorded for this code path:

- Image lists must not fetch original `data_base64`.
- Thumbnail variants should be generated at upload time, or lazily generated on first variant access and then cached.
- Frontend cards use `loading="lazy"`, `decoding="async"`, `srcset`/`sizes`, and stable `width`/`height`.
- Backend variant responses use `ETag`, `Cache-Control`, and `304 Not Modified`.
- The current storage backend is `db_base64` in `image_library_variants`; the table shape keeps `storage_backend`, `storage_key`, and `public_url` so object storage/CDN adapters can replace the DB backend later.

Current variants:

- `original`: original upload bytes.
- `thumb_160`: small picker thumbnail.
- `thumb_320`: card thumbnail.
- `preview_720`: modal preview.

Backfill command:

```bash
python tools/backfill_image_library_variants.py --dry-run --limit 500 --batch-size 50
python tools/backfill_image_library_variants.py --limit 500 --batch-size 50
```

