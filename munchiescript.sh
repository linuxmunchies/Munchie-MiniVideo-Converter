#!/bin/bash

input="$1"
temp="temp_video.mp4"
output="output.webp"

ffmpeg -i "$input" -vf "setpts=0.125*PTS,scale=480:-1" -an "$temp"
ffmpeg -i "$temp" -vf "fps=10" -c:v libwebp -lossless 0 -q:v 60 -loop 0 "$output"

rm "$temp"
echo "Done! Saved as $output"