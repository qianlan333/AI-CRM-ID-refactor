# D9.2 OpenClaw Legacy Move Map

This map started as the D9.2 future move map. D9.4 has now moved the metadata-only frozen marker into the archive package and retained `openclaw_service/` as a compatibility shim.

| current_path | future_path | move_phase | import_rewrite_required | runtime_role | default_next_imported | legacy_fallback_imported | shim_required | move_blocker | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `openclaw_service/` | `legacy_flask/openclaw_legacy/` | D9.4 | shim imports archive metadata only | compatibility shim | false | false | true | operational window and D9.5 shim-removal signoff | directory remains in place as shim |
| `openclaw_service/LEGACY_FROZEN.md` | `legacy_flask/openclaw_legacy/LEGACY_FROZEN.md` | D9.4 | no | frozen marker retained in shim and archive | false | false | true | production replacement evidence and rollback proof | source tree only had this legacy marker |
| `openclaw_service/__init__.py` | compatibility shim to `legacy_flask.openclaw_legacy` | D9.4 | yes | import compatibility only | false | false | true | D9.5 shim-removal gate | contains `LEGACY_COMPATIBILITY_SHIM` |
| `openclaw_service/README.md` | shim README | D9.4 | no | docs | false | false | true | D9.5 shim-removal gate | documents no runtime ownership |
| `docs/d9_5_openclaw_service_shim_removal_plan.md` | final shim-removal plan | D9.5 | static docs reference only | docs | false | false | false | D9.5.1 observation pending | planning only |
| `docs/d9_5_openclaw_final_reference_scan_plan.md` | final reference scan plan | D9.5 | static docs reference only | docs | false | false | false | final scan not captured | planning only |
| `docs/d9_5_openclaw_shim_removal_readiness_checklist.md` | final readiness checklist | D9.5 | static docs reference only | docs | false | false | false | signoff pending | planning only |
| `legacy_flask/openclaw_legacy/__init__.py` | archive package metadata | D9.4 | no | metadata only | false | false | false | D9.5 shim-removal gate | does not import `openclaw_service` |
| `legacy_flask/openclaw_legacy/README.md` | archive package README | D9.4 | no | archive docs | false | false | false | D9.5 shim-removal gate | archive package is not runtime owner |
| `legacy_flask/openclaw_legacy/LEGACY_FROZEN.md` | archived frozen marker | D9.4 | no | archive marker | false | false | false | D9.5 shim-removal gate | moved marker copy retained in archive |
| `legacy_flask/openclaw_legacy/MOVE_PENDING.md` | move status note | D9.4 | no | status docs | false | false | false | D9.5 shim-removal gate | records moved-with-shim status |
| `docs/d9_openclaw_legacy_adapter_retirement_plan.md` | update references after move | D9.2.4 | static docs reference only | docs | false | false | false | physical move not started | keep current path until implementation |
| `docs/d9_openclaw_legacy_dependency_inventory.md` | update inventory after move | D9.2.4 | static docs reference only | docs | false | false | false | physical move not started | inventory records pre-move state |
| `docs/d9_1_openclaw_legacy_import_freeze_plan.md` | update after move if shim exists | D9.2.4 | static docs reference only | docs | false | false | false | import freeze must remain PASS | D9.1 remains the import gate |
| `docs/d9_1_openclaw_import_allowlist.md` | update allowlist after shim is created | D9.2.4 | yes, if shim imports archive package | checker input | false | false | true | shim design not approved in D9.2 | default deny remains |
| `tools/check_d9_openclaw_legacy_retirement_readiness.py` | update static path checks after move | D9.2.4 | static path check only | checker | false | false | false | D9.2 implementation not started | no runtime import allowed |
| `tools/check_d9_1_openclaw_import_freeze.py` | update allowlist/static scan after move | D9.2.4 | static checker update | checker | false | false | false | import freeze must remain PASS | no runtime import allowed |
| `tools/check_d9_2_openclaw_legacy_move_readiness.py` | update or retire after move implementation | D9.2.4 | static checker update | checker | false | false | false | D9.3 skeleton exists, physical move not started | verifies no physical move in this slice |
| `tools/check_d9_3_openclaw_legacy_skeleton.py` | update or retire after move implementation | D9.4 | static checker update | checker | false | false | false | D9.3 acceptance pending | verifies skeleton only |
| `tests/test_d9_openclaw_legacy_retirement_readiness.py` | update assertions after move | D9.2.4 | static test update | tests | false | false | false | implementation not started | current test expects old path retained |
| `tests/test_d9_1_openclaw_import_freeze.py` | update static references if shim exists | D9.2.4 | static test update | tests | false | false | false | import freeze acceptance required | no runtime import allowed |
| `tests/test_d9_2_openclaw_legacy_move_readiness.py` | update or retire after move | D9.2.4 | static test update | tests | false | false | false | D9.3 skeleton exists, physical move not started | current test accepts no move or skeleton only |
| `tests/test_d9_3_openclaw_legacy_skeleton.py` | update or retire after move | D9.4 | static test update | tests | false | false | false | D9.3 acceptance pending | current test verifies skeleton only |
| `legacy_flask/app_factory.py` | no change expected | D9.2.4 | no | explicit legacy fallback app factory | false | true | false | no legacy archive runtime package yet | must not import `openclaw_service` |
| `legacy_flask/legacy_lockdown.py` | no change expected | D9.2.4 | no | fallback route guard | false | true | false | no legacy archive runtime package yet | allowed OpenClaw fallback route remains route-level only |
| `aicrm_next/integration_gateway/mcp_openclaw_adapters.py` | no move | retained | no | Next adapter replacement | false | false | false | real external evidence pending | primary path remains D7.7 boundary and does not import old legacy package |
| `aicrm_next/integration_gateway/mcp_openclaw_contracts.py` | no move | retained | no | Next adapter contract | false | false | false | real external evidence pending | primary path remains D7.7 boundary and does not import old legacy package |
| docs references to OpenClaw / MCP | update to archive path after move | D9.2.4 | static docs update | docs | false | false | false | docs rewrite plan incomplete until implementation | do not claim files moved yet |
| tests references to OpenClaw / MCP | update fixtures/assertions after move | D9.2.4 | static test update | tests | false | false | false | implementation not started | no runtime import allowed |
| checkers/static references | update path checks after move | D9.2.4 | static checker update | checker | false | false | false | implementation not started | no runtime import allowed |
