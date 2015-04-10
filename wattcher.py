#!/usr/bin/env python

import serial, time, datetime, sys
from xbee import xbee
import sensorhistory
import argparse

# Can also be turned on with passing '-d' to script
DEBUG = False

# Logging interval in seconds
LOG_INTVL = 30

# where we will store our flatfile data
LOGFILE = "powerdatalog.csv"

# Sensor calibration file
CALFILE = "calibration"

# the com/serial port the XBee is connected to
#SERIALPORT = "/dev/ttyAMA0"
SERIALPORT = "/dev/ttyUSB0"
BAUDRATE = 9600

# which XBee ADC has current draw data
CURRENTSENSE = 4

# which XBee ADC has mains voltage data
VOLTSENSE = 0

# +-170V is what 120Vrms ends up being (= 120*2sqrt(2))
MAINSVPP = 170 * 2

# conversion to amperes from ADC
CURRENTNORM = 15.5

# Twitter stuff
TWITTER = False
if TWITTER:
    import twitter
twitterusername = "username"
twitterpassword = "password"
# Simple timer for twitter makes sure we don't twitter > 1/day
twittertimer = 0

def TwitterIt(u, p, message):
    api = twitter.Api(username=u, password=p)
    print u, p
    try:
        status = api.PostUpdate(message)
        print "%s just posted: %s" % (status.user.name, status.text)
    except UnicodeDecodeError:
        print ("Your message could not be encoded.  Perhaps it " +
               "contains non-ASCII characters? ")
        print ("Try explicitly specifying the encoding with the  it " +
               "with the --encoding flag")
    except:
        print "Couldn't connect to Twitter!"

# This might be missing some args, I just wanted to get it out of
# the main loop. Might need a global declaration or two also.
def check_twitter():
    # We're going to twitter at midnight, 8am and 4pm
    # Determine the hour of the day (ie 6:42 -> '6')
    currhour = datetime.datetime.now().hour
    # twitter every 8 hours
    if (((time.time() - twittertimer) >= 3660.0) and
        (currhour % 8 == 0)):
        print "twittertime!"
        twittertimer = time.time();

        # sum up all the sensors' data
        wattsused = 0
        whused = 0
        for history in shists.sensorhistories:
            wattsused += history.avg_watthr()
            whused += history.dayswatthr
                
        message = ("Currently using "+str(int(wattsused))+" Watts,"+
                   str(int(whused))+" Wh today so far #tweetawatt")

        # write something ourselves
        if message:
            print message
            TwitterIt(twitterusername, twitterpassword, message)


def calibrate(ser, sensor_num):
    if DEBUG:
        print("in calibrate")

    # Grab one packet from the xbee or timeout
    cont = True
    while(cont):
        packet = xbee.find_packet(ser)
        if packet:
            cont = False
            print("Packet found!")
        else:
            print("Timeout waiting for packet, trying again..")

    xb = xbee(packet)

    x = 0
    # Skip the first sample since it's usually messed up.
    for i in range(len(xb.analog_samples) - 1):
        x += xb.analog_samples[i+1][CURRENTSENSE]
    x /= int(len(xb.analog_samples) - 1)

    print("Calibration value = {}" .format(x))
    vrefcalibration[sensor_num] = x
    cf = open(CALFILE, 'w')
    for i in range(len(vrefcalibration) - 1):
        cf.write("{}," .format(vrefcalibration[i]))
    cf.write("{}\n" .format(vrefcalibration[i+1]))
    cf.close()
    exit

def log_data(sensor, shist):
    now = time.strftime("%Y %m %d, %H:%M")

    print("{}, {}, {}\n" .format(now, sensor, shist.avg_watthr()))

    log.seek(0, 2)
    log.write("{}, {}, {}\n" .format(now, sensor, shist.avg_watthr))
    log.flush()

# the 'main loop' runs once a second or so.
# update_graph is a really stupid name for this fx
def update_graph(shists):
     
    # grab one packet from the xbee, or timeout
    packet = xbee.find_packet(ser)
    if not packet:
        return
    
    xb = xbee(packet)
    if DEBUG:
        print("xb.address_16 = {}" .format(xb.address_16))
        print("Parsed packet:")
        print xb
        print("")
        print("total_samples = {}" .format(xb.total_samples))
        
    # we'll only store n-1 samples since the first one is usually 
    # messed up
    voltagedata = [-1] * (len(xb.analog_samples) - 1)
    ampdata = [-1] * (len(xb.analog_samples) - 1)

    # Grab 1 thru n of the ADC readings
    for i in range(len(voltagedata)):
        voltagedata[i] = xb.analog_samples[i+1][VOLTSENSE]
        ampdata[i] = xb.analog_samples[i+1][CURRENTSENSE]

    if DEBUG:
        print("raw ampdata: {}" .format(ampdata))
        print("raw voltdata: {}" .format(voltagedata))

    # get max and min voltage and normalize the curve to '0'
    # to make the graph 'AC coupled' / signed
    min_v = 1024     # XBee ADC is 10 bits, so max value is 1023
    max_v = 0
    for i in range(len(voltagedata)):
        if (min_v > voltagedata[i]):
            min_v = voltagedata[i]
        if (max_v < voltagedata[i]):
            max_v = voltagedata[i]

    # figure out the 'average' of the max and min readings
    avgv = (max_v + min_v) / 2
    # also calculate the peak to peak measurements
    vpp =  max_v-min_v

    for i in range(len(voltagedata)):
        #remove 'dc bias', which we call the average read
        voltagedata[i] -= avgv
        # We know that the mains voltage is 120Vrms = +-170Vpp
        voltagedata[i] = (voltagedata[i] * MAINSVPP) / vpp

    # normalize current readings to amperes
    for i in range(len(ampdata)):
        # VREF is the hardcoded 'DC bias' value, its
        # about 492 but would be nice if we could somehow
        # get this data once in a while maybe using xbeeAPI
        if vrefcalibration[xb.address_16]:
            ampdata[i] -= vrefcalibration[xb.address_16]
        else:
            ampdata[i] -= vrefcalibration[0]
        # the CURRENTNORM is our normalizing constant
        # that converts the ADC reading to Amperes
        ampdata[i] /= CURRENTNORM
    
    # calculate instant. watts, by multiplying V*I for each sample
    # point
    wattdata = [0] * len(voltagedata)
    for i in range(len(wattdata)):
        wattdata[i] = voltagedata[i] * ampdata[i]

    if DEBUG:
        print("voltagedata: {}" .format(voltagedata))
        print("ampdata:  {}" .format(ampdata))
        print("wattdata: {}" .format(wattdata))

    # sum up the current drawn over one 1/60hz cycle
    avgamp = 0
    # 16.6 samples per second, one cycle = ~17 samples
    # close enough for govt work :(
    for i in range(17):
        avgamp += abs(ampdata[i])
    avgamp /= 17.0

    # sum up power drawn over one 1/60hz cycle
    avgwatt = 0
    # 16.6 samples per second, one cycle = ~17 samples
    for i in range(17):         
        avgwatt += abs(wattdata[i])
    avgwatt /= 17.0

    print("{}\tCurrent draw, in amperes: {}" .format(xb.address_16, 
                                                     avgamp))
    print("\tWatt draw, in VA: {}" .format(avgwatt))

    if (avgamp > 13):
        # hmm, bad data
        return

    shist = shists.find(xb.address_16)
    
    # Add up the delta-watthr used since last reading.
    # Figure out how many watt hours were used since last reading.
    elapsedseconds = time.time() - shist.lasttime
    dwatthr = (avgwatt * elapsedseconds) / (3600.0)
    shist.lasttime = time.time()
    print("\t\tWh used in last {} seconds: {}" 
          .format(elapsedseconds, dwatthr))
    shist.add_watthr(dwatthr)

    if ((time.time() - shist.timer) >= LOG_INTVL):
        log_data(xb.address_16, shist)
        shist.reset_timer()
        

#------#
# main #
#------#

# Process command line args
parser = argparse.ArgumentParser()
parser.add_argument('-c', dest='sensor_to_cal', action='store',
                    metavar="SENSOR#",
                    help="sensor number to calibrate")
parser.add_argument('-d', dest='DEBUG', action='store_true',
                    help="turn on debugging")
args = parser.parse_args()

if args.DEBUG:
    DEBUG = True

# open up the serial port to get data transmitted to xbee
ser = serial.Serial(SERIALPORT, BAUDRATE)

# Load sensor calibration data
cf = open(CALFILE, 'r')
line = cf.readline()
vrefcalibration = [int(x) for x in line.split(",")]
cf.close()

if args.sensor_to_cal != None:
    calibrate(ser, int(args.sensor_to_cal))

# Open and init datalogging file
try:
    log = open(LOGFILE, 'r+')
except IOError:
    # didn't exist yet
    log = open(LOGFILE, 'w+')
    log.write("#Date, time, sensornum, avgWatts\n");
    log.flush()
            
shists = sensorhistory.SensorHistories(log)
print shists

while True:
    update_graph(shists)

    if TWITTER:
        check_twitter()
