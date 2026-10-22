# Required manual actions

1. **Lesson access:** supply the enrolled Academy lesson URL/text for the exact sample source registration recipe, REST/JDBC contract and Composer/Grok smoke prompt. The public syllabus exposes only the lesson title. User-provided corrections govern current preparation; missing instructions are not guessed.
2. **Memory:** current Docker allocation is 7.66 GiB and available WSL memory is below 8 GiB. No changes were made. When ready, authorize/perform the minimum WSL/Docker allocation change and ensure 8 GiB is actually available without stopping unrelated services automatically. The project uses 8 GiB as a conservative interpretation of the organizer's 8 GB requirement.
3. **Docker Hub access:** `docker login` required interactive authentication; one Freemium server pull was denied. Ask the organizer to grant access to the actual `zetaris/lightning-*` v2.4.1.0-latest images. Only retry after access changes; use the four-service pull command in SETUP.md. No licence/Cloud bundle route is substituted.
4. **Initialize Freemium account:** once all four containers can run, use the README's actual `/home/zetaris/lightning/bin/dev-account.sh` helper. In the external runtime directory, read private values interactively rather than typing a password into shell history:

   ```bash
   read -rp 'Account email: ' zetaris_email
   read -rsp 'New unique password: ' zetaris_password; printf '\n'
   read -rp 'Organization: ' zetaris_org
   docker compose -p quorum-zetaris -f compose.json exec zetaris-server /home/zetaris/lightning/bin/dev-account.sh "$zetaris_email" "$zetaris_password" "$zetaris_org"
   unset zetaris_email zetaris_password zetaris_org
   ```

   The vendor helper accepts positional arguments, so the password can briefly appear in local process inspection. Run only in the trusted local environment, do not record the session, and never use the README's public password. A stdin-based interface is not assumed.
5. **Register/query sample dataset:** follow the exact lesson recipe in GUI `http://localhost:9001`. Supply its real registered-dataset SELECT, matching external JDBC JAR and account in private configuration. Set the documented REST JSON endpoint separately. Run diagnostics and require an actual row; open ports or `SELECT 1` are insufficient. The recipe/JAR are not yet available.
6. **Cursor Composer/Grok:** keep the current login and model settings. Open Quorum through Ubuntu-20.04 WSL2. Select the lesson's Composer model in Agent/Composer and repeat with its Grok selection, using existing sponsor entitlement only. A preparatory read-only prompt is: “Read README.md and reports/readiness.md. Make no file changes. Run git status --short --branch and ./scripts/doctor.sh in the WSL integrated terminal. Explain which integrations are blocked and why.” Use the lesson's exact prompt when supplied. Confirm both responses, WSL terminal and Source Control work. Do not enter Meterless keys in Cursor settings, buy credits or use provider inference credits for development.

   After actually observing success, you may store a private external JSON record and point `CURSOR_ACCEPTANCE_FILE` to it. Record `observed_at` and booleans `composer_passed`, `grok_passed`, `wsl_terminal_passed`, `git_passed`. Do not mark unperformed checks true. Diagnostics label this as user-recorded acceptance, not an automated model test.
7. **Meterless/Nemotron:** obtain the exact sponsored API base URL, API key and Nemotron model ID; set `METERLESS_BASE_URL`, `METERLESS_API_KEY`, `NEMOTRON_MODEL` only in private configuration. No defaults are guessed. Standard diagnostics do not infer or spend credits. After confirming the sponsor route/contract, explicitly run `./scripts/verify-all.sh --inference` for one capped test.

Normal full diagnostics: `cd ~/Quorum && ./scripts/verify-all.sh`.

No project/track is selected. Environment preparation does not establish final hackathon eligibility or submission compliance.
