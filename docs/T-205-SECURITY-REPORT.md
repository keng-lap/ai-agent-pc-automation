# T-205 Security Verification Report

## Scope

This report covers backend controls owned by T-205 under `docs/PHASE-2.md`:
SEC-01 to SEC-09, SEC-11, SEC-12, and SEC-14 to SEC-16. SEC-10 remains owned by
T-202, SEC-13 is covered by T-203 and B-12, ST-22 is owned by T-204, and ST-24
is owned by T-202.

## Implementation and test evidence

| Requirement | Implementation and evidence |
|-------------|------------------------------|
| SEC-01 | Backend startup accepts loopback bind hosts only (`test_loopback_hosts_are_accepted`, `test_non_loopback_host_is_rejected`); Angular dev server host is asserted to be `127.0.0.1` (`test_frontend_dev_server_binds_to_loopback`). |
| SEC-02 | Exact backend Host allow-list is enforced before routing (`test_foreign_or_inexact_hosts_are_rejected`, `test_empty_host_is_rejected_and_exact_loopback_hosts_are_accepted`, `test_missing_host_is_rejected`). |
| SEC-03 | Exact Origin allow-list; missing Origin is rejected for state-changing methods (`test_foreign_or_inexact_origins_are_rejected`, `test_exact_frontend_origins_are_accepted`, `test_missing_origin_is_rejected_for_post_but_allowed_for_health`). |
| SEC-04 | No CORS middleware or preflight handler (`test_preflight_is_not_handled_and_no_cors_headers_are_sent`, `test_response_has_no_cors_headers_or_cookies`). |
| SEC-05 | State-changing methods require JSON media type; UTF-8 charset parameter is accepted (`test_non_json_state_changing_requests_are_rejected`, `test_json_charset_parameter_is_accepted`). |
| SEC-06 | Host, Origin, and content-type checks reject cross-site browser requests. No cookies or ambient credentials are issued (`test_response_has_no_cors_headers_or_cookies`). |
| SEC-07 | OpenAPI GET allow-list is `/health`; every `/api` route is POST-only (`test_openapi_get_routes_match_allow_list_and_api_routes_are_post_only`). |
| SEC-08 | Generic 404/405/422/500 errors do not expose internal details (`test_unexpected_exception_returns_generic_error_and_scrubs_message`, existing chat validation tests). |
| SEC-09 | Request content is not logged (`test_no_message_content_is_logged`, `test_unexpected_exception_returns_generic_error_and_scrubs_message`). |
| SEC-11 | No token or secret was added to `.env.example`; runtime dependencies are unchanged (`test_example_configuration_has_no_token_or_secret`, `test_runtime_dependencies_remain_unchanged`). |
| SEC-12 | Invalid backend or frontend port configuration fails closed (`test_environment_configuration_rejects_invalid_ports`, `test_application_factory_fails_closed_on_invalid_ports`). |
| SEC-14 | `/docs`, `/redoc`, and `/openapi.json` are available only in development (`test_docs_endpoints_are_disabled_outside_development`). |
| SEC-15 | Bodies over 16 KiB are rejected before parsing, including streamed bodies without Content-Length (`test_oversized_body_is_rejected_before_json_parsing`, `test_chunked_body_limit_rejects_body_without_content_length`). |
| SEC-16 | No token or authorization header is required in Phase 2 (`test_exact_frontend_origins_are_accepted`). |

## Security test matrix

| Test IDs | Evidence in this task |
|----------|-----------------------|
| ST-01 to ST-04 | Host allow-list, including missing and empty Host |
| ST-05 to ST-09 | Origin allow-list and exact comparisons |
| ST-10 to ST-12 | Missing Origin behavior and JSON content type |
| ST-13 to ST-14 | Preflight refusal, no CORS headers, no cookies |
| ST-15 to ST-16 | Method failure order and OpenAPI GET allow-list |
| ST-17 | 16 KiB limit for declared and streamed bodies |
| ST-18 to ST-19 | Existing malformed request and internal exception tests |
| ST-20 to ST-21 | Invalid port and non-loopback startup configuration |
| ST-22 | Owned by T-204; not part of this report |
| ST-23 | Every `/api` route is POST-only in OpenAPI |
| ST-24 | Owned by T-202; not part of this report |

## Mutation evidence

Each mutation below was applied temporarily, the named focused test was run, and
the test failed as expected. The original file bytes were restored after each
probe. This checks that the suite detects removal or weakening of the control.

| Mutated control | Focused test that caught the mutation |
|-----------------|--------------------------------------|
| SEC-01 backend loopback restriction | `test_non_loopback_host_is_rejected` |
| SEC-01 Angular dev-server loopback | `test_frontend_dev_server_binds_to_loopback` |
| SEC-02 Host allow-list | `test_foreign_or_inexact_hosts_are_rejected` |
| SEC-03 Origin allow-list | `test_foreign_or_inexact_origins_are_rejected` |
| SEC-04 CORS prohibition | `test_preflight_is_not_handled_and_no_cors_headers_are_sent` |
| SEC-05 JSON content type | `test_non_json_state_changing_requests_are_rejected` |
| SEC-07 API method allow-list | `test_openapi_get_routes_match_allow_list_and_api_routes_are_post_only` |
| SEC-08 generic error body | `test_unexpected_exception_returns_generic_error_and_scrubs_message` |
| SEC-09 log scrubbing | `test_unexpected_exception_returns_generic_error_and_scrubs_message` |
| SEC-11 secret exclusion | `test_example_configuration_has_no_token_or_secret` |
| SEC-11 runtime dependencies | `test_runtime_dependencies_remain_unchanged` |
| SEC-12 fail-closed port configuration | `test_application_factory_fails_closed_on_invalid_ports` |
| SEC-14 docs disabled in production | `test_docs_endpoints_are_disabled_outside_development` |
| SEC-15 body-size limit | `test_oversized_body_is_rejected_before_json_parsing` |
| SEC-16 no authorization token | `test_exact_frontend_origins_are_accepted` |

## Verification status

`scripts/test.ps1` passed: 73 backend tests, Ruff, and 19 frontend tests. Pytest
and Ruff emitted non-fatal cache-write warnings because their existing cache
directories are not writable in this workspace. All 15 focused security
mutations listed above were caught by their corresponding tests.

T-204 integration check ST-22 remains outstanding for its owning task; ST-24
remains evidenced by T-202. This report does not claim Phase 2 is complete.

## Task completion record

- Task: T-205, Local web security implementation and verification.
- Branch: `feat/t-205-local-web-security`.
- Base commit: `9bc931b7489735fa4d5c64df9e06d66af0b6fce8`.
- Implementation commit: `58eeec470ed0181f6d4055aa978f30aebb3a6382`.
- Pull request: [#16](https://github.com/keng-lap/ai-agent-pc-automation/pull/16), merged on 2026-10-23.
- Merge commit on `main`: `449adb4f3e20ea0b3eecdd2766a2582df0ced036`.
- Verification: `scripts/test.ps1` passed 73 backend tests, Ruff, and 19 frontend tests; all 15 listed mutation probes were detected.
- Product Owner manual checks: not recorded for T-205. ST-22 and end-to-end/manual checks belong to T-204; ST-24 belongs to T-202.
- GitHub CI status/workflow runs for the merge commit: none were reported when checked.
- Next task: T-204 remains not started and requires an explicit start from the Product Owner.
