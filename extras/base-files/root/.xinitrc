#!/bin/sh

echo "xinitrc: start" | /usr/bin/dbgwrite
echo "xinitrc: HOME=${HOME} DISPLAY=${DISPLAY} PATH=${PATH}" | /usr/bin/dbgwrite

(
	echo "xinitrc: xclock start" | /usr/bin/dbgwrite
	xclock -geometry 100x100+20+20 2>&1 | /usr/bin/dbgwrite
	echo "xinitrc: xclock exit $?" | /usr/bin/dbgwrite
) &

(
	echo "xinitrc: xterm start" | /usr/bin/dbgwrite
	xterm -geometry 80x24+150+20 2>&1 | /usr/bin/dbgwrite
	echo "xinitrc: xterm exit $?" | /usr/bin/dbgwrite
) &

echo "xinitrc: twm exec" | /usr/bin/dbgwrite
exec twm 2>&1 | /usr/bin/dbgwrite
