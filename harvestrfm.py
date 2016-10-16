import serial
import json
import linecache
import sys
import paho.mqtt.client as mqtt
from time import sleep, gmtime, localtime, strftime
from datetime import datetime, timedelta

import ConfigParser
import ssl

import ctypes
import logging


def search_dictionaries(key, value, list_of_dictionaries):
    return [element for element in list_of_dictionaries if element[key] == value]

# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
    logging.info("Connected with result code "+str(rc))
# The callback for when a PUBLISH message is received from the server.
def on_publish(client, userdata, mid):
	logging.debug( "Publish Mid: "+ str(mid))

def on_disconnect(client, userdata, rc):
    if rc != 0:
        logging.info("Unexpected disconnection.")
    quit()

def PrintException():
    exc_type, exc_obj, tb = sys.exc_info()
    f = tb.tb_frame
    lineno = tb.tb_lineno
    filename = f.f_code.co_filename
    linecache.checkcache(filename)
    line = linecache.getline(filename, lineno, f.f_globals)
    logging.warning( 'EXCEPTION IN ({}, LINE {} "{}"): {}'.format(filename, lineno, line.strip(), exc_obj))

def jsonlog(d):
	logging.debug(d)

def strlog(s):
	logging.debug(s)

config = ConfigParser.ConfigParser({'port': '1883', 'defaulttopic':'sensors/','user':'wthr','pass':'password'})
config.read('/usr/local/harvest/harvestrfm.cfg')

if config.has_option("harvester", "logfile"):
	logging.basicConfig(filename=config.get("harvester", "logfile"),level=logging.DEBUG)
else:
	logging.basicConfig(level=logging.DEBUG)

rfm_lib=ctypes.cdll.LoadLibrary('/home/wthr/rfm22b-master/rfm.so')

rfm_lib.rf_init(0)

datadict = [{'Prefix': 'A', 'Length': 25, 'Keys':['Idx','ID'], 'Topic':'Sensor', 'Algo':[0,0]},{'Prefix': 'B', 'Length': 18, 'Keys':['Cycle','Temperature'], 'Topic':'Sensor', 'Algo':[4,1]},{'Prefix': 'Y', 'Length': 16, 'Keys':['Reset','Sensors'], 'Topic':'Board', 'Algo':[3,0]},{'Prefix': 'Z', 'Length': 16, 'Keys':['Reset','Battery'], 'Topic':'Board','Algo':[3,2]}]

basetopic="unconfigured/"

buffer = ctypes.create_string_buffer(80)
rfpoll = rfm_lib.rf_poll
rfpoll.argtypes = [ctypes.c_char_p, ctypes.c_int]

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

dt = datetime.now() + timedelta(hours=1)
boot=strftime("%Y-%m-%d %H:%M:%S", localtime())

topic=default_topic+'harvester/boot'
mqttc.publish(topic, boot)

while run:
        status = rfpoll(buffer, 80)
        if (status>0):
                logging.debug(buffer.value)
                blen=len(buffer.value)
                try:
                        partr=buffer.value.split()
                        rssi =0.56*int(partr[1])-128.8;
                except ValueError:
                        rssi=0
                        logging.warning( "Could not convert data to RSSI.")

                parta=partr[0].split(":")

                partb=parta[1].split("=")

                partc=partb[1].split(",")

                itmdict=search_dictionaries('Prefix',parta[0], datadict)[0]

                if (blen==itmdict['Length']):
                        try:
                                idx=int(partb[0])
                                sidx=0
				stridx=str(idx)
                        	if (config.has_section(stridx)):
                                	mq_name=config.get(stridx, 'name')
                                	mq_topic=config.get(stridx, 'topic')
				else:
					mq_name=stridx
					mq_topic=basetopic+'/'+stridx

                                topic=mq_topic+str(idx)+'/RSSI'

                                logging.debug( mq_name+':')

                                for i,v in enumerate(partc):
                                        alg=itmdict['Algo'][i]
                                        if (alg==1):
                                                value=int(v)/10.0
                                        elif (alg==2):
                                                value=int(v,16)/204.7
                                        elif (alg==3):
                                                value=int(v,16)
                                        elif (alg==4):
                                                value=int(v,16)
                                                sidx=(value&0xff00)>>8
                                                value=value&0x00ff
                                        else:
                                                value=v

                                        topic=mq_topic+'/RSSI'
                                        logging.debug(topic+'='+str(rssi))
                                        mqttc.publish(topic, rssi)

                                        topic=mq_topic+'/'+itmdict['Topic']+str(sidx)+'/'+itmdict['Keys'][i]
                                        logging.debug(topic+'='+str(value))
					mqttc.publish(topic, value)
                        except ValueError:
				PrintException()
                else:
                        logging.warning("Wrong length "+str(blen)+" for packet type "+parta[0])

	if (datetime.now() > dt):
    		dt = datetime.now() + timedelta(hours=1)
		hbt=strftime("%Y-%m-%d %H:%M:%S", gmtime())

		topic=default_topic+'/hbt'
		mqttc.publish(topic, hbt)
		logging.debug("Hearbeat @ "+hbt)
	mqttc.loop(2)
	sleep(0.5)


