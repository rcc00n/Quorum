# Manual actions

1. **Cursor:** finish any first-run/login prompts. Open the installed Windows Cursor. If required, use its official WSL extension to connect to `Ubuntu-20.04`, then open `/home/raccoon/Quorum`. Confirm the remote indicator shows that distribution. In the integrated terminal run `pwd`, `uname -r`, `git status --short --branch` and `./scripts/doctor.sh`. Confirm the Source Control view recognizes Quorum and shows its branch. This GUI/remote/terminal/Git acceptance remains untested until observed; executable presence or a process launch is insufficient.
2. **Zetaris:** obtain an organizer-provided instance/account/org ID, or the official platform archive, matching `.env`, registry credentials and licence/evaluation access. No such access was found in the current environment or Quorum configuration. Fill private connection values. Ask the operator for the exact supported health endpoint and data source discovery commands. Verify `SELECT 1 AS one` returns one row with 1 and inspect actual supported sources. For local use, check available RAM, port mappings and official preflight before pulling/starting anything.
3. **Nemotron:** sign in at NVIDIA's model page, generate a free/trial API key if available, and add it to `.env.local` as `NVIDIA_API_KEY`. Do not enable paid services. Run the verifier once to execute the capped real request.
4. **Meterless inference (optional):** obtain an authorized supported runtime URL/token if needed. The installed memory/state references do not provide inference. No local models, GPU runtimes or paid editions are needed for the completed reference checks.
5. **Docker Desktop integration (optional):** the working native Linux Engine is sufficient. Desktop's WSL distributions were stopped during the audit. If Desktop specifically becomes required, inspect its WSL integration settings and plan any backend change separately; do not switch away from the existing backend automatically.

Full diagnostics: `cd ~/Quorum && ./scripts/verify-all.sh`. Exit 2 means blocked/untested work remains; exit 1 indicates a failure.

If GitHub authentication expires, use `gh auth login --hostname github.com --git-protocol https --web` and `gh auth setup-git`. Never put its token in Quorum.

No project or track has been selected. Check current event rules and deadlines separately before final submission; environment preparation is not submission compliance.
