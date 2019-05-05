#!/bin/sh

# This shell library is meant to be used with `set -e`.

# Create a GTK bookmark for `target`.
# Call this only as the amnesia user.
add_gtk_bookmark_for() {
   local target
   target=$(echo "$1" | sed 's, ,%20,g')

   mkdir -p "${HOME}/.config/gtk-3.0"

   if [ $# -ge 2 ]; then
      title="$2"
      echo "file://$target $title" >> "${HOME}/.config/gtk-3.0/bookmarks"
   else
       echo "file://$target" >> "${HOME}/.config/gtk-3.0/bookmarks"
   fi
}
