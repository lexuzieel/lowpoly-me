#!/bin/sh
# Stamp a fresh build id into web/index.html (cache busting for GitHub Pages' 10 min cache)
id=$(date +%Y%m%d%H%M%S)
sed -i "s/const BUILD = \"[^\"]*\";/const BUILD = \"$id\";/" "$(dirname "$0")/web/index.html"
echo "build $id"
