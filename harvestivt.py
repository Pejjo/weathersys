#! /usr/bin/python

import serial
import json
import linecache
import sys
import paho.mqtt.client as mqtt
from time import sleep, gmtime, strftime
import ssl
import os

import ConfigParser


connected=False

# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
    connected=True
    print("Connected with result code "+str(rc))

# The callback for when a PUBLISH message is received from the server.
def on_publish(client, userdata, mid):
        print "Publish Mid: "+ str(mid)

def on_disconnect(client, userdata, rc):
    if rc != 0:
        print("Unexpected disconnection.")
        connected=False

def check_connection():
    if (connected==False):
        print("Reconnecing\n\r")
        mqttc.connect(config.get("harvester", "server"), config.get("harvester", "port"), 60)


def PrintException():
    exc_type, exc_obj, tb = sys.exc_info()
    f = tb.tb_frame
    lineno = tb.tb_lineno
    filename = f.f_code.co_filename
    linecache.checkcache(filename)
    line = linecache.getline(filename, lineno, f.f_globals)
    print 'EXCEPTION IN ({}, LINE {} "{}"): {}'.format(filename, lineno, line.strip(), exc_obj)

def jsonlog(d):
	print (d)

def strlog(s):
	print (s)



cfgname=os.path.splitext(__file__)[0]+".cfg"

print "Reading default config file " + cfgname


config = ConfigParser.ConfigParser({'baud': '9600', 'port': '1883', 'defaulttopic':'sensors/'})
config.read(cfgname)


ser=serial.Serial(config.get("harvester", "serial"), config.get("harvester", "baud"), timeout=0)
print(ser.name, ' opened.\n')
mqttc = mqtt.Client(config.get("harvester", "clientname"))
mqttc.on_connect = on_connect
mqttc.on_disconnect = on_disconnect
mqttc.on_publish = on_publish
# the server to publish to, and corresponding port
mqttc.tls_set('/usr/local/harvest/cert/ca.crt', certfile='/usr/local/harvest/cert/wthr.crt', keyfile='/usr/local/harvest/cert/wthr.key', cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLSv1, ciphers=None)
mqttc.tls_insecure_set(True)
mqttc.username_pw_set(config.get("harvester", "user"), password=config.get("harvester", "pass"))


mqttc.connect(config.get("harvester", "server"), config.get("harvester", "port"), 60)

default_topic=config.get("harvester", "defaulttopic")

run=True
jdata = None
while run:
	line=ser.readline()
	if len(line)>0:
		try:
			cvsdata=line.split(';')
		except ValueError:
			PrintException()

		print "Len" + str(len(cvsdata))
		print cvsdata

		jdata=0
	
		if len(cvsdata)==37:
			for idx, cvsitem in enumerate(cvsdata):
				rawdata=cvsitem.strip()
				stridx=str(idx)
				if (config.has_section(stridx)):
					mq_name=config.get(stridx, 'name')
					mq_topic=config.get(stridx, 'topic')
					datatype=config.get(stridx, 'datatype')
					
					try:					
						if (datatype=='INT'):
							data=int(rawdata)
						elif (datatype=='DECIINT'):
							data=int(rawdata)/10.0
						elif (datatype=='BOOL'):
                                        		data=int(rawdata)
						else:
                                        		data=rawdata
							print "Unknown datatype " + str(idx) + "Data: " + rawdata + "\r\n"
					except ValueError:
                                                        PrintException()
				else:
					mq_name="Unknown"+stridx
					datatype="none"
					mq_topic=default_topic+"/unknown/"+stridx
					print '['+ stridx + ']' + " missing in config file. Please add "
				
				ctime=strftime("%Y-%m-%d %H:%M:%S", gmtime())
				print ctime, " - ", stridx, ", ", mq_name, ", ", datatype, ", ", rawdata, "\r\n"
						
				try:

#							mqttc.publish(mq_topic, mq_name)
							mqttc.publish(mq_topic, data)
				except ValueError:
					PrintException()
#						print dat['data']
		else:
			print 'Error: ', cvsdata
	mqttc.loop(2)
	sleep(0.5)


