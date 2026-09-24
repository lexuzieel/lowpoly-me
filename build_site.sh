#!/bin/sh
# Assemble the Pages site: latest web/ at the root, every snapshot versions/vN at /vN.
# Snapshots are stored without songs; each gets the tracks its page expects.
set -e
cd "$(dirname "$0")"
out=${1:-_site}
rm -rf "$out"; mkdir -p "$out"
cp -r web/. "$out/"
for d in versions/v*; do
  v=$(basename "$d"); dst="$out/$v"
  cp -r "$d" "$dst"
  page="$dst/index.html"
  if grep -q 'song_${SONG}' "$page"; then      # v8+: numeric ids
    cp audio/opt1_liquid_dnb.mp3 "$dst/song_1.mp3"; cp audio/ru2_liquid_dnb.mp3 "$dst/song_2.mp3"
  elif grep -q 'song_${LANG}' "$page"; then    # v7: en / ru
    cp audio/opt1_liquid_dnb.mp3 "$dst/song_en.mp3"; cp audio/ru2_liquid_dnb.mp3 "$dst/song_ru.mp3"
  elif grep -q 'song.mp3' "$page"; then        # v2-v6: the first Russian track
    cp audio/song.mp3 "$dst/song.mp3"
  fi
done
# every asset a page references must exist next to it
fail=0
for page in "$out/index.html" "$out"/v*/index.html; do
  dir=$(dirname "$page")
  for f in me.glb bg.jpg lipsync.json song.mp3; do
    grep -q "\"$f\"\|($f)\|url($f)" "$page" && [ ! -f "$dir/$f" ] && { echo "MISSING $dir/$f"; fail=1; }
  done
  for pair in 'song_${SONG}.mp3:song_1.mp3 song_2.mp3' 'lipsync_${SONG}.json:lipsync_1.json lipsync_2.json' \
              'song_${LANG}.mp3:song_en.mp3 song_ru.mp3' 'lipsync_${LANG}.json:lipsync_en.json lipsync_ru.json'; do
    pat=${pair%%:*}; files=${pair#*:}
    if grep -qF "$pat" "$page"; then for f in $files; do [ -f "$dir/$f" ] || { echo "MISSING $dir/$f"; fail=1; }; done; fi
  done
done
[ $fail = 0 ] && echo "site ok: $(ls -d "$out"/v* | wc -l) versions, $(du -sh "$out" | cut -f1)"
exit $fail
