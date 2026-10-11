@echo off
REM Local ARM cross-build for the cudy-wr3000v2 lab modules and the luofu kernel image.
REM No GitHub Actions. Usage:  local-build.bat [target]
REM   modules: luofu-fmc luofu-clk luofu-pinctrl luofu-pcie luofu-wifi
REM   kernel : kernel   (builds zImage + luofu-r116.dtb + luofu-uImage into build/luofu-kernel-image)
setlocal
set MOD=%1
if "%MOD%"=="" set MOD=luofu-fmc
wsl -d Ubuntu -u root -- bash /mnt/c/Users/ShibbityShwab/Documents/GitHub/cudy-wr3000v2/build/tmp/local-build.sh %MOD%
endlocal
