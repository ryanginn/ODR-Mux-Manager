#!/usr/bin/env bash
# Build a private ffmpeg for DMB: libx264 (H.264) + libfdk_aac (HE-AAC v1/v2).
# It goes into its own prefix (default /opt/odr-mux-manager/ffmpeg) and is NOT put on the system PATH,
# so the distribution ffmpeg stays untouched. odr-mux-manager is pointed at it via tool_paths.
#
#   sudo packaging/build-ffmpeg.sh [PREFIX]
#
# Note: libfdk_aac is "nonfree": a binary built with it may be used, but not redistributed.
set -euo pipefail

PREFIX="${1:-/opt/odr-mux-manager/ffmpeg}"
FFMPEG_VERSION="${FFMPEG_VERSION:-7.1.1}"
FDK_VERSION="${FDK_VERSION:-v2.0.3}"
JOBS="${JOBS:-$(nproc 2>/dev/null || echo 2)}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "Building ffmpeg $FFMPEG_VERSION with libfdk_aac $FDK_VERSION and libx264 into $PREFIX"

if command -v apt-get >/dev/null; then
    apt-get install -y -qq build-essential pkg-config nasm yasm autoconf automake libtool \
        libx264-dev git curl ca-certificates >/dev/null
fi

mkdir -p "$PREFIX"
export PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig:${PKG_CONFIG_PATH:-}"

# fdk-aac (static, inside the prefix)
git clone -q --depth 1 --branch "$FDK_VERSION" https://github.com/mstorsjo/fdk-aac.git "$WORK/fdk-aac"
( cd "$WORK/fdk-aac" && autoreconf -fi >/dev/null && \
  ./configure --prefix="$PREFIX" --disable-shared --enable-static --with-pic >/dev/null && \
  make -j"$JOBS" >/dev/null && make install >/dev/null )

# ffmpeg
curl -fsSL "https://ffmpeg.org/releases/ffmpeg-$FFMPEG_VERSION.tar.xz" -o "$WORK/ffmpeg.tar.xz"
tar -xf "$WORK/ffmpeg.tar.xz" -C "$WORK"
( cd "$WORK/ffmpeg-$FFMPEG_VERSION" && \
  ./configure --prefix="$PREFIX" \
      --enable-gpl --enable-nonfree --enable-libx264 --enable-libfdk-aac \
      --pkg-config-flags=--static \
      --extra-cflags="-I$PREFIX/include" --extra-ldflags="-L$PREFIX/lib" \
      --disable-doc --disable-ffplay --disable-debug >/dev/null && \
  make -j"$JOBS" >/dev/null && make install >/dev/null )

"$PREFIX/bin/ffmpeg" -hide_banner -encoders 2>/dev/null | grep -q libfdk_aac || { echo "build finished but libfdk_aac is missing" >&2; exit 1; }
echo "Done: $PREFIX/bin/ffmpeg (libx264 + libfdk_aac). It is not on the system PATH."
