#!/usr/bin/env bash
# a script to generate the icons
# requires imagemagick
# the icon should be present as "icon.svg" in the same directory

convert -background none icon.svg -gravity center -resize 48x48 -extent 46x46 -bordercolor "#ffffff00" -border 1 icon.png &&
convert -background none icon.svg -gravity center -resize 192x192 -extent 192x192 -bordercolor "#ffffff00" -border 1 icon_highres.png
