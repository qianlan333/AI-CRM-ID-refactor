# D9.1 OpenClaw Import Allowlist

Default policy is deny. This table records static references and any explicit fallback exception. AI-CRM Next runtime imports are not allowed.

| path | import_pattern | allowed | reason | expires_in_phase | risk | notes |
| --- | --- | --- | --- | --- | --- | --- |
| `aicrm_next/**` | `import openclaw_service` / `from openclaw_service` | false | AI-CRM Next must use D7.7 MCP/OpenClaw adapter boundary | D9.1 | direct legacy dependency | checker blocks regardless of other rows |
| `experiments/ai_crm_next/src/aicrm_next/**` | `import openclaw_service` / `from openclaw_service` | false | experiments mirror must follow Next boundary | D9.1 | mirror drift | checker treats as runtime code |
| `legacy_flask/**` | `import openclaw_service` / `from openclaw_service` | false | legacy fallback should not grow new direct OpenClaw package imports | D9.2 | fallback runtime coupling | any future exception needs manual review |
| `wecom_ability_service/**` | `import openclaw_service` / `from openclaw_service` | false | compatibility shim and legacy modules should not add old package imports | D9.2 | old package coupling | any future exception needs manual review |
| `tools/check_d9_openclaw_legacy_retirement_readiness.py` | static path/reference scan | true | checker only verifies package existence and old import absence | D9.5 | false confidence if checker imports runtime code | no direct package import |
| `tools/check_d9_1_openclaw_import_freeze.py` | static import scanner | true | checker parses imports and allowlist; it does not import old package | D9.5 | parser must avoid string false positives | no direct package import |
| `tests/test_d9_openclaw_legacy_retirement_readiness.py` | static path assertions | true | tests verify package exists and remains frozen | D9.5 | test could drift into runtime import | direct package import remains disallowed |
| `tests/test_d9_1_openclaw_import_freeze.py` | static path/import-freeze assertions | true | tests verify import freeze behavior and synthetic blocker | D9.5 | synthetic fixture must stay isolated | direct package import remains disallowed |
| `openclaw_service/__init__.py` | `from legacy_flask.openclaw_legacy` | true | D9.4 transitional compatibility shim keeps old imports from crashing | D9.5 | shim could be mistaken for runtime owner | no AI-CRM Next import may target this shim |
| `tests/test_d9_4_openclaw_legacy_move.py` | `import openclaw_service` smoke | true | targeted test verifies the compatibility shim import only | D9.5 | test must not call external OpenClaw behavior | import smoke only |
| `tools/check_d9_5_openclaw_shim_removal_readiness.py` | static readiness checker | true | checker verifies the shim still exists and imports no old runtime package | D9.5.1 | checker must not call OpenClaw | static checks only |
| `tests/test_d9_5_openclaw_shim_removal_readiness.py` | static readiness tests | true | tests verify planning-only shim retention and checker behavior | D9.5.1 | tests must not remove shim | no external call |
| `docs/**` | historical `openclaw_service/` reference | true | retirement docs need historical path references and gates | D9.5 | docs may be mistaken for runtime guidance | static reference only |
| `openclaw_service/LEGACY_FROZEN.md` | self-reference | true | frozen marker documents retention state | D9.5 | stale retention note | package remains in place |
| `scripts/**` | `import openclaw_service` / `from openclaw_service` | false | scripts must not add runtime dependency on the old package | D9.3 | validation script coupling | static path text requires manual review |
