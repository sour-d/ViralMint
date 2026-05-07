#!/usr/bin/env bash
# Download a static ffprobe binary matching the host platform.
#
# Why: imageio_ffmpeg (our bundled ffmpeg source) only ships ffmpeg, not
# ffprobe. Several backend services (thumbnail_service, ffmpeg_service,
# ytdlp_service, clip_extractor) shell out to "ffprobe" and fail in the
# packaged desktop build without it.
#
# Output: desktop/scripts/vendor/ffprobe  (or ffprobe.exe on Windows)
#         PyInstaller picks it up via viralmint.spec's `binaries` list.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENDOR="$REPO_ROOT/desktop/scripts/vendor"
mkdir -p "$VENDOR"

OS="$(uname -s)"
ARCH="$(uname -m)"

# Skip if we already fetched a valid binary — keeps local rebuilds fast.
if [[ -x "$VENDOR/ffprobe" ]] || [[ -f "$VENDOR/ffprobe.exe" ]]; then
  echo "==> ffprobe already vendored at $VENDOR, skipping download"
  ls -lh "$VENDOR"/ffprobe* 2>/dev/null || true
  exit 0
fi

case "$OS" in
  Darwin)
    # osxexperts.net is maintained by the same author as evermeet.cx and
    # publishes per-arch ffprobe zips. evermeet.cx itself only builds x86_64.
    if [[ "$ARCH" == "arm64" ]]; then
      URL="https://www.osxexperts.net/ffprobe71arm.zip"
    else
      URL="https://www.osxexperts.net/ffprobe71intel.zip"
    fi
    echo "==> Fetching macOS ffprobe ($ARCH) from $URL"
    curl -fL --retry 3 -o "$VENDOR/ffprobe.zip" "$URL"
    unzip -o -q "$VENDOR/ffprobe.zip" -d "$VENDOR"
    rm "$VENDOR/ffprobe.zip"
    chmod +x "$VENDOR/ffprobe"
    ;;

  Linux)
    # johnvansickle.com: canonical static ffmpeg/ffprobe build for Linux x64.
    URL="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
    echo "==> Fetching Linux static ffprobe from $URL"
    curl -fL --retry 3 -o "$VENDOR/ffmpeg-linux.tar.xz" "$URL"
    tar -xJf "$VENDOR/ffmpeg-linux.tar.xz" -C "$VENDOR"
    # The tarball unpacks as ffmpeg-<version>-amd64-static/{ffmpeg,ffprobe,…}.
    # We only want ffprobe — drop the rest.
    mv "$VENDOR"/ffmpeg-*-amd64-static/ffprobe "$VENDOR/ffprobe"
    rm -rf "$VENDOR"/ffmpeg-*-amd64-static "$VENDOR/ffmpeg-linux.tar.xz"
    chmod +x "$VENDOR/ffprobe"
    ;;

  MINGW*|MSYS*|CYGWIN*)
    # gyan.dev essentials: the de-facto Windows static build. Ships ffprobe.exe
    # inside ffmpeg-<version>-essentials_build/bin/.
    URL="https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    echo "==> Fetching Windows ffprobe from $URL"
    curl -fL --retry 3 -o "$VENDOR/ffmpeg-win.zip" "$URL"
    unzip -o -q "$VENDOR/ffmpeg-win.zip" -d "$VENDOR"
    mv "$VENDOR"/ffmpeg-*-essentials_build/bin/ffprobe.exe "$VENDOR/ffprobe.exe"
    rm -rf "$VENDOR"/ffmpeg-*-essentials_build "$VENDOR/ffmpeg-win.zip"
    ;;

  *)
    echo "fetch-ffprobe.sh: unsupported OS: $OS" >&2
    exit 1
    ;;
esac

echo "==> ffprobe vendored:"
ls -lh "$VENDOR"/ffprobe*
