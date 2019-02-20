#! /usr/bin/python
import serial
import json
import linecache
import sys
import paho.mqtt.client as mqtt
from time import time,sleep,ctime, gmtime, strftime
import configparser
import ssl
import os
from array import *
import logging
import logging.handlers
import argparse
import re
# Defaults
LOG_FILENAME = "/var/log/weathersys/harvestsmq.log"
LOG_LEVEL = logging.INFO  # Could be e.g. "DEBUG" or "WARNING"

DEFAULT_SMT_GAIN = 212.7659574
DEFAULT_SMT_OFFS = -0.320

# Define and parse command line arguments
parser = argparse.ArgumentParser(description="SMTQuad data poller")
parser.add_argument("-l", "--log", help="file to write log to (default '" + LOG_FILENAME + "')")

# If the log file is specified on the command line then override the default
args = parser.parse_args()
if args.log:
        LOG_FILENAME = args.log

# Configure logging to log to a file, making a new file at midnight and keeping the last 3 day's data
# Give the logger a unique name (good practice)
logger = logging.getLogger(__name__)
# Set the log level to LOG_LEVEL
logger.setLevel(LOG_LEVEL)
# Make a handler that writes to a file, making a new file at midnight and keeping 3 backups
handler = logging.handlers.TimedRotatingFileHandler(LOG_FILENAME, when="midnight", backupCount=3)
# Format each log message like this
formatter = logging.Formatter('%(asctime)s %(levelname)-8s %(message)s')
# Attach the formatter to the handler
handler.setFormatter(formatter)
# Attach the handler to the logger
logger.addHandler(handler)
def s8(value):
    return -(value & 0x80) | (value & 0x7f)

# Make a class we can use to capture stdout and sterr in the log
class MyLogger(object):
        def __init__(self, logger, level):
                """Needs a logger and a logger level."""
                self.logger = logger
                self.level = level

        def write(self, message):
                # Only log if there is a message (not just a new line)
                if message.rstrip() != "":
                        self.logger.log(self.level, message.rstrip())

# Replace stdout with logging to file at INFO level
#sys.stdout = MyLogger(logger, logging.INFO)
# Replace stderr with logging to file at ERROR level
#sys.stderr = MyLogger(logger, logging.ERROR)


# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
    print("Connected with result code "+str(rc))
    if rc != 0:
        logger.error("Unexpected disconnection, code "+str(rc))
    else :
        logger.debug("Connected successfully")

# The callback for when a PUBLISH message is received from the server.
def on_publish(client, userdata, mid):
        print("Publish Mid: "+ str(mid))

def on_disconnect(client, userdata, rc):
        logger.error("Unexpected disconnection.")


def AddCrc(crc,n):
  crc=crc^n
  for bitnumber in range(0,8):
    if ( crc & 0x01) : 
      crc = ( crc >> 1 ) ^ 0x8c
    else :
      crc = ( crc >> 1 )
  #print hex(crc & 0xFF)
  return crc & 0xFF

def chkcrc(str):
#  print(str)
  crc=0
  for x in str:
    x=ord(x)
    crc=AddCrc(crc,x)
  return crc

cfgname=os.path.splitext(__file__)[0]+".cfg"

print("Reading default config file " + cfgname)

config = configparser.ConfigParser({'baud': '38400', 'port': '1883', 'defaulttopic':'sensors/'})
config.read(cfgname)


ser=serial.Serial(config.get("harvester", "serial"), config.get("harvester", "baud"), timeout=20)
logger.info(ser.name+ ' opened.\n')
logger.info("Connect " +config.get("harvester", "server")+ ":"+str(config.get("harvester", "port")))
mqttc = mqtt.Client(config.get("harvester", "clientname"))
mqttc.on_connect = on_connect
mqttc.on_disconnect = on_disconnect
#mqttc.on_publish = on_publish

# the server to publish to, and corresponding port
# the server to publish to, and corresponding port
#mqttc.tls_set('/usr/local/harvest/cert/ca.crt', certfile='/usr/local/harvest/cert/wthr.crt', keyfile='/usr/local/harvest/cert/wthr.key', cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLSv1, ciphers=None)
#mqttc.tls_insecure_set(True)
#mqttc.username_pw_set(config.get("harvester", "user"), password=config.get("harvester", "pass"))


mqttc.connect(str(config.get("harvester", "server")), int(config.get("harvester", "port")), 60)

default_topic=config.get("harvester", "defaulttopic")
try:
	mqttc.loop_start()
except:
	logger.exception("Mqtt loop")


run=True

while run:
	line=ser.readline().strip()
# Parse input data
	if len(line)>0:
		try:
			[datapart,crcpart]=line.split('!')
			if (chkcrc(datapart)==int(crcpart,16)):
				splitdta=re.findall("^#(\d{2})Ch:(\d{2})-(\w*)=(\S*)!(\w{2})",line)
			else :
				logger.warning("CRC error: "+line)
				splitdta=[]
		except:
			logger.exception("Parse error")
			splitdta=[]
			pass
#		print (line, splitdta)
		type=''
		if (len(splitdta)==1): #Looks good
			splitdta=splitdta[0]
			if (len(splitdta)==5):
				try:
					if (splitdta[2]=='SMT'):
						type='smt'
						chanel=int(splitdta[1])
						intval=int(splitdta[3],16)
						if intval==0:
							dc=float('NaN')
						else:
							dc=1.0*intval/(1024*64)
					elif (splitdta[2]=='DHT'):
						type="dht"
						chanel=int(splitdta[1])
						vals=array('B')
						matches=re.findall("^T:([0-9,a-f]{2}).([0-9,a-f]{2}).H:([0-9,a-f]{2}).([0-9,a-f]{2})",splitdta[3])[0]						
						for n in matches:
							curbyte=int(n,16)&0xff
							vals.append(curbyte)
						if (vals[0]&0x80): #Negative
							hexval=((vals[0]&0x7f)<<8)+vals[1] # Reasemble
							intval=int(hexval/10)
							decval=hexval%10						
							tmpval=(intval+(decval/10.0))*(-1.0)
						else: #Plus
							hexval=((vals[0]&0x7f)<<8)+vals[1] # Reasemble
							intval=int(hexval/10)
							decval=hexval%10
							tmpval=intval+(decval/10.0)

#						print (hexval, intval, decval,tmpval)
						hexval=((vals[2]&0x7f)<<8)+vals[3] # Reasemble
						intval=int(hexval/10)
						decval=hexval%10
						humval=s8(intval)+(decval/10.0)
#						print (hexval, intval, decval, humval)
#						if not defined(tmpval):
				
#							print("type=",type, " tmp=",tmpval, " hum=", humval)
					
					elif (splitdta[2][0:2]=='AD'):
						type='adc'
						channel=chanel=int(splitdta[1])
						adch=int(splitdta[2][2:4])
						intval=int(splitdta[3],16)
						val=5.0*intval/1024
						crcval=0
#						print( type, channel,val, crcval)


					else:
						type="err"
						logger.warning( "Err2: "+ line )
				except ValueError:
					logger.exception("Parse")
		else:
			logger.warning( "Unparsable line: "+ line)


# Serial parsing done. Now process and publish
		if (type!=''):	#Valid values
			chkey=type+str(chanel)
#			print(chkey)		
			if (config.has_section(chkey)):
				try:
					if config.has_option(chkey,'ignore'):
						if config.getint(chkey, 'ignore')==1:
							type='ignore'
					mq_name=config.get(chkey, 'name')
					mq_topic=config.get(chkey, 'topic')
				except:
					logger.exception("Config error")
					type='ignore'
				ctime=strftime("%Y-%m-%d %H:%M:%S", gmtime())

				if (type=='smt'):
					if (config.has_option(chkey, 'gain')):
						gain=config.getfloat(chkey, 'gain')
					else:
						gain=DEFAULT_SMT_GAIN
					if (config.has_option(chkey, 'offset')):
						offset=config.getfloat(chkey, 'offset')
					else:
						offset=DEFAULT_SMT_OFFS
					if ((dc>0.1) and (dc<0.94)):
						tempval=(dc+offset)*gain
					else:
						tempval=float('NaN')
#					print( mq_name, dc, tempval, offset)
					try:
						mqttc.publish(mq_topic+'/name', mq_name,qos=2)
						mqttc.publish(mq_topic+'/temp', tempval,qos=2) 
						mqttc.publish(mq_topic+'/int', intval,qos=2)
						mqttc.publish(mq_topic+'/dc', dc,qos=2)
					except ValueError:
						logger.exception("Publish SMT Value Error")
					except:
						logger.exception("Publish SMT general")
				elif (type=='dht'):
#                                        print( ctime, " - ", mq_name, ", ", type, ", ", tmpval, ", ",humval)
                                        try:
                                                mqttc.publish(mq_topic+'/name', mq_name, qos=2)
                                                mqttc.publish(mq_topic+'/temperature', float(tmpval),qos=2)
                                                mqttc.publish(mq_topic+'/humidity', float(humval),qos=2)
                                        except ValueError:
                                                logger.exception("Publish DHT Value error")
                                        except:
                                                logger.exception("Publish DHT general")
				elif (type=='adc'):
#                                        print( ctime, " - ", mq_name, ", ", type, ", ", tmpval, ", ",humval)
					try:
						mqttc.publish(mq_topic+'/name', mq_name, qos=2)
						mqttc.publish(mq_topic+'/voltage', float(val),qos=2)
					except ValueError:
						logger.exception("Publish ADC Value error")
					except:
						logger.exception("Publish ADC general")

				elif (type=='ignore'):
					pass


			else:
				logger.info("Config missig for "+chkey)
#				mq_name='Unknown'
#				mq_topic=default_topic+str(chanel)
	sleep(1)

