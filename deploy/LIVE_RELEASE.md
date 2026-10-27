# Verified live release — 27 October 2026 UTC

Owner: rcc00n / Codex. Canonical shared tracking: [Issue #2](https://github.com/rcc00n/Quorum/issues/2).
This is release evidence, not a second rulebook. Earlier milestones remain historical.

## Live access and exact release

- Public URL: https://quorum.raccncode.com
- Genuine installed edition: https://quorum.raccncode.com/dashboard?date=2026-10-26
- Topic: https://quorum.raccncode.com/topics/immigration-southern-border?date=2026-10-26
- Investigation: https://quorum.raccncode.com/events/83fd23a203a0?date=2026-10-26
- Production source: `63418421c1c0909dc0d7dfa1b451da3eed1bcc76`, release `20261027-live-r3`.
- Archive SHA256: `f270d738a2fad033856017113c03c4ccbfe8cdd4c4f2126127e95fee76580827`; source and compiled artifacts bound by build receipt v2.
- Dedicated ordinary judge account exists; credentials are only in owner-private storage, for the HackOS form. No password is published here. Open registration remains available under the existing product decision.
- Feed/API/event require authentication. The reader serves signed-in users; it is not restricted to a new judge-only role.

## Infrastructure and SSH

Keep the **existing Vultr VPS**, `144.202.24.190`, for Django/Next/Nginx and private SQLite auth/preferences. Builds run locally. Preserve collection/PostgreSQL and the official Zetaris bundle on the owners' proven machines; do not migrate them. [Infrastructure diagram, official price comparison, capacity/security and provider limitations](INFRASTRUCTURE.md).

**Additional monthly server cost: $0.** Existing Vultr subscription, model/provider usage and tax totals cannot be established without invoices. No new purchase or paid inference was performed. A new processing host is unnecessary for the immutable-edition portal; the current shared 4-GB VPS is unsuitable for adding the default Zetaris stack.

The supplied ed25519 key belongs to **Anastasia**, as she confirmed in [Issue #2 comment 6431963633](https://github.com/rcc00n/Quorum/issues/2#issuecomment-6431963633), and matched `SHA256:1YQtaPzfPuVR9sbmIjAQzbCxhGk5op14+/mO2eFbLmM` exactly. Account `yelysei-deploy` has locked password, key authentication and **full passwordless sudo (root-equivalent)**. Its home/.ssh/authorized_keys modes are 0750/0700/0600; validated sudoers file is 0440. Owner root authorized_keys is byte-identical to its restricted backup. Server-side sudo returns UID 0. Anastasia confirms successful key-holder login from her Mac. The account name remains `yelysei-deploy`; Yelysei has no separate installed key. This corrects the original handoff's attribution to Yelysei; no access was changed by the documentation correction.

```sh
ssh -i ~/.ssh/id_ed25519 -o IdentitiesOnly=yes yelysei-deploy@144.202.24.190
sudo -n id -u  # expected: 0
```

No private SSH key was requested. A fingerprint alone cannot be installed; only the complete matching public key was installed.

## Accepted genuine edition and publication boundaries

The untouched 26-Oct `immigration-southern-border` v1 original and sidecar passed native acceptance with no issues and were installed as `quorum` on the production host:

| Binding | Value |
| --- | --- |
| Snapshot SHA256 | `55452aab927ff7a5076d35401ed15e1a8c117a9beeb200fa8ebc4e81a49ed000` |
| Sidecar SHA256 | `2fd1b7614bb7137550fa74590e0a5456832b18c3d60863476cb4e1cac4f99bd2` |
| Producer commit | `55a8e26ad0c215280a0f4f239264a0c68a15fbbf` |
| Producer config SHA256 | `db76d41509aeea40670a0211c8fc10bb4372b7b4051e8719d480757565e191db` |
| Counts | 1 story, 9 claims, 14 evidence rows, 19 roundup entries, 174 trace rows, 0 snapshot errors |
| Corpus boundary | `2026-10-26T09:30:00Z`, provisional/clamped |
| Generated / expires | `2026-10-26T14:15:31Z` / `2026-10-27T12:00:00Z` |

Directory `/var/lib/quorum/editions` and every descendant directory: owner quorum, 0700. Files: 0600. Exact snapshot, sidecar and installation metadata are integrity-bound; incomplete/modified/fictional production editions fail closed. Reader variables are enabled; the separate proposal publisher remains disabled and its root unset. No public upload endpoint exists.

Clean metadata acceptance is **not** independent execution/source-text certification. Native report retains `execution_verified=false`, `source_text_verified=false`, `published=false` (the acceptance command does not publish); `installed=true` separately records the reader installation. The browser shows **Provisional corpus as of…** and **Requires editorial review**. The producer article's statement composition does not pass the article rendering guard, so the honest claims/evidence presentation is retained; no prose or verdict was rewritten. At recorded expiry the edition becomes stale without disappearing. Historical v4 remains unaccepted and was not installed.

Catalog: four approved demo IDs, 40 reviewed source definitions. No collection database or topic row was written. Three display labels are human-readable fallbacks from approved IDs, not asserted database labels. Processing schedules remain on owner machines; website requests never trigger model spend.

## Verification and rollback

- Local Next production build and typecheck passed; package rejected private/runtime/link paths and matched source/artifact hashes.
- Actual target-host Django run: 93 tests run, OK, 5 explicit private-original skips; migration drift/production checks passed, no migration applied. Deployment tests 16 and diagnostics/tooling tests 10 passed.
- Full local reasoning: 2,803 passed, 84 skipped, 2 expected failures. Engine-backed/contract memory checks 44 passed; pinned H-MEM reference conformance 13/13, exit 0. No provider requests in these tests.
- Doctor: 15 PASS / 0 FAIL / 1 BLOCKED / 1 NOT_TESTED. Verify: 31 PASS / 0 FAIL / 2 BLOCKED / 1 NOT_TESTED. Blocks are startup RAM headroom and routine Nightshift model credentials. Actual local official Zetaris SELECT 1, bundled sample query and verify.sh passed; these do not prove a new full-corpus federation run.
- Source CI [40434686930](https://github.com/rcc00n/Quorum/actions/runs/40434686930) and final integration CI [40434951526](https://github.com/rcc00n/Quorum/actions/runs/40434951526): portal/Chrome and combined-python successful. Earlier #32/#35 CI and associated owner reviews are retained.
- Genuine installed-edition regression forces server UTC+14 and browser UTC−10: local date label matches the browser and zero page errors; original story/trace unchanged.
- **Public production HTTPS/Chromium:** UI login/logout, anonymous feed/event denial, ordinary judge staff denial, CSRF rejection, Secure/HttpOnly session cookie; actual feed/story/roundup, exact 174 trace decisions, attributed evidence/source URLs/reviewer decisions, all four rating modes, 1440/768/390 layouts without horizontal overflow, no fictional banner or DEBUG preview links, zero page errors.
- All eight previously issued regular/admin credentials authenticated over production HTTPS with correct staff boundaries. No passwords rotated. All nine pre-existing accounts/preferences survived deployment; adding the judge makes ten.
- Both Quorum services were restarted: the existing judge session, four topic preferences and exact genuine edition/feed persisted; UI signout and anonymous restrictions passed afterwards.
- TLS certificate verifies successfully (Let's Encrypt, valid through 2027-01-20). Final external login is HTTP 200; API/web services active.
- Guarded backups are restricted and SQLite integrity-checked. A judge-enabled consistent backup was also securely copied outside the VPS into owner-private storage.
- Actual code/static rollback to the prior release and guarded reapply passed without database restoration. Only quorum-api/quorum-web were restarted. All 24 unrelated container identities/start timestamps match the preflight baseline. Nginx/firewall/global runtimes and existing secrets/databases were preserved.

Rollback uses the exact previous release and static backup recorded in private `rollback.json` under `/var/lib/quorum/backups/upgrade-*`, with `/opt/quorum/upgrade.lock`, only Quorum units stopped, symlink/static restored, services started and HTTPS/auth checked. No automatic DB restoration: migrations are forbidden on this path, and concurrent writes must survive. The pre-existing 09f5325 release is retained too.

## End-to-end evidence states

| Component | Implemented / tested | Genuine execution evidence | Production observation |
| --- | --- | --- | --- |
| Collectors / PostgreSQL | Merged collection contracts/tests | Owner's post-cut dump and collection receipts | Runs on collection owner's environment; not independently re-executed here |
| Zetaris Lightning | Official bundle and API adapter tested | Committed sanitized corpus receipt and owner two-machine reconciliation; local sample SQL separately passed | Preserved owner deployment, not moved to VPS |
| Reasoning | Merged graph; 2,803 local tests pass | Accepted genuine original/sidecar declares corpus Zetaris | Original exactly projected through API/browser |
| NVIDIA | Two-lane client/tests | Installed 26-Oct run declares 1,435 calls: 1,287 Lightning + 148 Ultra, 0 model errors | Output served; provider/billing audit not re-executed |
| Meterless/Nightshift | Merged route/receipt/guard code | Separate owner-reported 202-receipt showcase and 188-call H-MEM check | Not falsely attributed to the installed direct-NVIDIA edition |
| H-MEM | Engine/sidecar tests and conformance pass | Owner reports three writes; live engine recall pending 27-Oct runs | Not hosted on portal; Build-rule completion not claimed |
| Immutable edition | Native clean acceptance, exact hashes and permissions | Genuine original installed unchanged | DEPLOYED, signed-in browser verified |
| Django / Next / browser | CI + real HTTP/type/browser checks | Authenticated real original throughout | DEPLOYED; HTTPS/restart/rollback checked |
| Collection/reasoning schedulers | Owner runbook and sequential runner merged | Next post-cut run scheduled by owners | No website processing scheduler or model credentials installed |

The entire fresh Collection → Zetaris → Nightshift → NVIDIA → H-MEM recall → accepted 27-Oct edition chain is not independently demonstrated by this session. Sponsor statements remain scoped to the evidence above.

## Merge status and new commits

Reasoning #29 → collection #28 → web #23–#27 → README #30 → reader #31 were integrated in that dependency order with owner reviews retained. #22 was already merged. Documentation conflicts retained every owner's decision; calibrated threshold 4 remains intact. #32/#33 delivered the portal hardening; #34 fixed GitHub README precedence; #35/#36 fixed target-test isolation; #37/#38 delivered the verified hydration fix. Old draft #6 and raw-evidence review #21 remain open and are not release dependencies; their owner gates were not bypassed.

Small independent changes in this execution (merge commits preserved separately):

| Commit | Change |
| --- | --- |
| c384761 | Initial deployment scope/evidence report |
| 1b7bb50 | Verified additive SSH key helper and tests |
| 5763902 | Reviewed integration assembly and coordination history |
| 98696f6 | Fail-closed accepted edition integrity |
| 03a06e7 | Private edition directory/file permissions |
| a5c5c3c | Official provider assessment and hosting choice |
| 58f2c2b | Genuine evidence/trace projection and browser harness |
| 384cb1e | Dated judge dashboard links |
| f0565a9 | Hosted Chrome acquisition fix, all tests retained |
| 0775d08 | Honor recorded expiry while retaining stale content |
| b2caf98 | Isolate target-host tests from production data |
| 689e30f | Local date hydration and cross-timezone regression |
| 292ea74 | Distinguish actual NVIDIA route from separate Nightshift evidence |

README availability commit `f9ad078` and later evidence-only documentation commits accompany this report; production source stays pinned above.

## Remaining owner dependencies and recommendation

- **GO:** genuine authenticated 26-Oct provisional edition, evidence/reviewer/trace demonstration on the public site.
- **NO-GO:** claiming independently certified source text/provider execution, full live Nightshift/H-MEM recall chain, accepted historical v4, or completed hackathon submission.
- Yelysei: execute agreed 27-Oct runbook on the already-proven Windows environment, Meterless route/H-MEM guard and stop rules; push each producer commit; deliver exact originals/sidecars by 14:00Z (14:30Z latest). Correct writer statement composition; keep unsupported spectrum.readings off. Provide his own complete public key if separate VPS access is needed; the installed key belongs to Anastasia.
- Anastasia: provide 10:30Z post-cut dump; accept/install each received edition only through the real gates, update shared Issue #2 and verify the signed-in dated site by 18:00Z. No AWS move needed. Actual topic display labels can replace fallback labels through a reviewed export.
- Vadim: enter private judge credentials and dated live URL into the HackOS form; final human submission/rights/workspace checks and submission before 23:45Z remain. Existing invoice/model usage totals need billing records if an all-in cost is required.
- Existing media are preserved and unchanged. Video/slides remain last priority; no completed submission is claimed.

## Separate teammate messages (drafts)

**Yelysei:** Anastasia's verified key is installed for `yelysei-deploy@144.202.24.190`, with full passwordless sudo; owner access is preserved. Connect with `ssh -i ~/.ssh/id_ed25519 -o IdentitiesOnly=yes yelysei-deploy@144.202.24.190`, then `sudo -n id -u` (0). Production is 6341842; the genuine 26-Oct edition is live, including exact evidence and 174 trace steps. Your separate key is not installed; execute the agreed 27-Oct Windows/Nightshift/H-MEM runbook; deliver originals/sidecars and producer commits. No historical v4 acceptance is implied.

**Anastasia:** Your reviewed web/reader/catalog changes and README fix #34 are merged. Existing Vultr hosts the portal; reader variables and quorum-owned 0700 editions are configured. The genuine 26-Oct original passed native acceptance and public browser tests (1 story/19 roundup/174 trace); four demo topics/40 sources and a private ordinary judge account are ready. Existing nine accounts are preserved. Please provide the post-cut dump and install only cleanly accepted 27-Oct files; preserve provisional/review labels and check the dated site by 18:00Z. #37/#38 fix cross-timezone hydration.

**Vadim:** Live product: https://quorum.raccncode.com/dashboard?date=2026-10-26, production 6341842. Judge login is in your private credential file; put it only into HackOS. CI, real HTTPS browser, old account roles, restart persistence and actual rollback passed. Anastasia's key/sudo are configured under yelysei-deploy, and she confirms successful login; Yelysei has no separate installed key. No new server or inference charges; extra server cost $0. GO for this honest provisional demo; pending 27-Oct originals, full sponsor/recall certification and human submission checks remain explicit.
