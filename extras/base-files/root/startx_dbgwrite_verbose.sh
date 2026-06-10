#!/bin/bash

# Create the named pipe using Python
rm -f /tmp/Xorg.log
python3 -c "import os; os.mkfifo('/tmp/Xorg.log')"

# Pipe the log to the E9 console in the background
/usr/bin/dbgwrite < /tmp/Xorg.log &

# Launch startx with the log redirected to the named pipe
startx -- -retro -ac -logfile /tmp/Xorg.log -logverbose 7 2>&1 | /usr/bin/dbgwrite
