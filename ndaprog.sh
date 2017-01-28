# Board has AVR109 compatible bootloader @ 19200 Baud. (from xboot-Noda6-19k)
echo -en '#b\r' > /dev/ttytsP3 
sleep 4
avrdude -p atxmega16a4 -P /dev/ttytsP3 -c avr109 -b 19200 -e -U flash:w:noda6.hex

