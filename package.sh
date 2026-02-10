#!/bin/bash
set -e
VERSION=${1:-"v0.1.0"}
PLATFORMS=("darwin-amd64" "darwin-arm64")
echo "Packaging mac_maintenance $VERSION"
mkdir -p dist
for platform in "${PLATFORMS[@]}"; do
    platform_dir="dist/mac_maintenance-$platform"
    mkdir -p "$platform_dir"
    cp mac_maintenance.py "$platform_dir/"
    cp README.md LICENSE "$platform_dir/" 2>/dev/null || true
    cat > "$platform_dir/install.sh" << 'INSTALL'
#!/bin/bash
set -e
INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/bin}"
mkdir -p "$INSTALL_DIR"
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required"
    exit 1
fi
cp mac_maintenance.py "$INSTALL_DIR/mac-maintenance"
chmod +x "$INSTALL_DIR/mac-maintenance"
echo "✓ Installed to $INSTALL_DIR/mac-maintenance"
INSTALL
    chmod +x "$platform_dir/install.sh"
    cd dist
    tar -czf "mac_maintenance-$VERSION-$platform.tar.gz" "mac_maintenance-$platform"
    rm -rf "mac_maintenance-$platform"
    cd ..
done
echo "✓ All packages created in dist/"
