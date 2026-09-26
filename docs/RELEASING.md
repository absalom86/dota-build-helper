# Publishing an update

Users install **DotaBuildHelper-Setup.exe** once. From v0.1.14 onward, the packaged app checks the public GitHub latest stable release at startup, at most once per day. It shows an update button without interrupting gameplay. Users choose **Download**, then **Install and restart** after their match. Downloads must pass SHA-256 and size verification before installation. **Later** hides the reminder for a day; **Updates → Check now** remains available.

Settings, the encrypted STRATZ key and search history stay in `%LOCALAPPDATA%\DotaBuildHelper`, outside the installation folder. Users should not uninstall first or delete that folder. Updates to a portable copy install the application; the original portable file is unchanged. Launch the installed copy from the Start menu afterward.

## Owner release steps

1. Update the version in `dota_helper/version.py`, `pyproject.toml`, `build-installer.ps1`, and `packaging/installer.iss`. Run `python scripts/check-release-version.py`.
2. Commit the reviewed code, including `.github/workflows/release.yml`, and push it to `main`.
3. Tag that commit, for example `git tag v0.1.14`, then `git push origin v0.1.14`.
4. GitHub Actions **Build Windows release** runs tests, builds and smoke-tests the EXE, builds the installer, checks install/reinstall/settings retention, and uploads a **draft release**. You can retry an existing tag through **Run workflow**, specifying its exact tag. Published releases cannot be replaced by the workflow.
5. Review the draft's release notes and artifacts. Download the installer and test it on a second Windows PC, including the update/restart flow. Publish it as the latest stable release when ready. Drafts and prereleases are not offered to users.

Keep these exact release asset names: `DotaBuildHelper-Setup.exe`, `DotaBuildHelper.exe`, and `SHA256SUMS.txt`. The updater uses GitHub's asset SHA-256 digest, with the checksums file as a fallback. The workflow needs Actions enabled and uses its built-in GitHub token; do not add a STRATZ key or personal GitHub token to releases or builds.

The first upgrade from older versions is manual: run the new installer over the existing installation. Later versions can use the in-app updater. Manual fallback: [latest installer](https://github.com/absalom86/dota-build-helper/releases/latest/download/DotaBuildHelper-Setup.exe).

Checksums detect corrupt or mismatched downloads; they do not replace Windows code signing. These builds remain unsigned unless a signing certificate is configured separately. A failed download leaves the running app intact. Installer failures can be retried from the downloaded file or the release page.
