#!/usr/bin/env python

import serial, time, datetime, sys
from xbee import xbee
import sensorhistory
import argparse

# Can also be turned on with passing '-d' to script
DEBUG = False

# Logging interval in seconds
LOG_INTVL = 120

# where we will store our flatfile data
LOGFILENAME = "powerdatalog.csv"

# Sensor calibration file
CALFILE = "calibration"

# for graphing stuff
GRAPHIT = True
if GRAPHIT:
    import wx
    import numpy as np
    import matplotlib
    matplotlib.use('WXAgg')
    from pylab import *

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

# Load sensor calibration data
cf = open(CALFILE, 'r')
line = cf.readline()
vrefcalibration = [int(x) for x in line.split(",")]
cf.close()

# conversion to amperes from ADC
CURRENTNORM = 15.5

# how many samples to watch in the plot window, 1 hr @ 2s samples
NUMWATTDATASAMPLES = 1800

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

# the 'main loop' runs once a second or so.
# update_graph is a really stupid name for this fx
def update_graph(idleevent):
    global avgwattdataidx, shists, twittertimer, DEBUG
     
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

    # grab 1 thru n of the ADC readings, referencing the ADC constants
    # and store them in nice little arrays
    for i in range(len(voltagedata)):
        voltagedata[i] = xb.analog_samples[i+1][VOLTSENSE]
        ampdata[i] = xb.analog_samples[i+1][CURRENTSENSE]

    if DEBUG:
        print "ampdata: "+str(ampdata)
        print "voltdata: "+str(voltagedata)

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

    #print "Voltage, in volts: ", voltagedata
    #print "Current, in amps:  ", ampdata

    # calculate instant. watts, by multiplying V*I for each sample
    # point
    wattdata = [0] * len(voltagedata)
    for i in range(len(wattdata)):
        wattdata[i] = voltagedata[i] * ampdata[i]

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

    # Print out our most recent measurements
    print str(xb.address_16)+"\tCurrent draw, in amperes: "+str(avgamp)
    print "\tWatt draw, in VA: "+str(avgwatt)

    if (avgamp > 13):
        # hmm, bad data
        return

    if GRAPHIT:
        # Add the current watt usage to our graph history
        avgwattdata[avgwattdataidx] = avgwatt
        avgwattdataidx += 1
        if (avgwattdataidx >= len(avgwattdata)):
            # If we're running out of space, shift the first 10% out
            tenpercent = int(len(avgwattdata)*0.1)
            for i in range(len(avgwattdata) - tenpercent):
                avgwattdata[i] = avgwattdata[i+tenpercent]
            for i in range(len(avgwattdata) - tenpercent, len(avgwattdata)):
                avgwattdata[i] = 0
            avgwattdataidx = len(avgwattdata) - tenpercent

    # Retreive the history for this sensor
    shist = shists.find(xb.address_16)
    #print shist
    
    # Add up the delta-watthr used since last reading.
    # Figure out how many watt hours were used since last reading.
    elapsedseconds = time.time() - shist.lasttime
    dwatthr = (avgwatt * elapsedseconds) / (3600.0)
    shist.lasttime = time.time()
    print("\t\tWh used in last {} seconds: {}" 
          .format(elapsedseconds, dwatthr))
    shist.add_watthr(dwatthr)
    
    # Determine the minute of the hour (ie 6:42 -> '42')
    #currminute = (int(time.time())/60) % 10
    # Figure out if its been five minutes since our last save
    #if (((time.time() - shist.timer) >= 60.0)
    #    and (currminute % 5 == 0)
    #    ):
    if ((time.time() - shist.timer) >= LOG_INTVL):
        avgwattsused = shist.avg_watthr()
        now = time.strftime("%Y %m %d, %H:%M")
        print("{}, {}, {}\n" 
              .format(now, shist.sensornum, shist.avg_watthr()))
        #print (time.strftime("%Y %m %d, %H:%M")+","+
        #       str(shist.sensornum)+", "+
        #       str(shist.avg_watthr())+"\n")
               
        # Lets log it! Seek to the end of our log file
        if logfile:
            logfile.seek(0, 2)
            logfile.write("{}, {}, {}\n" .format(now, shist.sensornum,
                                                 shist.avg_watthr()))
            #logfile.write(time.strftime("%Y %m %d, %H:%M")+", "+
            #              str(shist.sensornum)+", "+
            #              str(shist.avg_watthr())+"\n")
            logfile.flush()
            
        shist.reset_timer()
        
    if TWITTER:
        check_twitter()

    if GRAPHIT:
        # Redraw our pretty picture
        fig.canvas.draw_idle()
        # Update with latest data
        wattusageline.set_ydata(avgwattdata)
        voltagewatchline.set_ydata(voltagedata)
        ampwatchline.set_ydata(ampdata)
        # Update our graphing range so that we always see all the data
        maxamp = max(ampdata)
        minamp = min(ampdata)
        maxamp = max(maxamp, -minamp)
        mainsampwatcher.set_ylim(maxamp * -1.2, maxamp * 1.2)
        wattusage.set_ylim(0, max(avgwattdata) * 1.2)


# open our datalogging file
logfile = None
try:
    logfile = open(LOGFILENAME, 'r+')
except IOError:
    # didn't exist yet
    logfile = open(LOGFILENAME, 'w+')
    logfile.write("#Date, time, sensornum, avgWatts\n");
    logfile.flush()
            
# open up the serial port to get data transmitted to xbee
ser = serial.Serial(SERIALPORT, BAUDRATE)

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

if args.sensor_to_cal != None:
    calibrate(ser, int(args.sensor_to_cal))

if GRAPHIT: 
    # Create an animated graph
    fig = plt.figure()
    # with three subplots: line voltage/current, watts and watthr
    wattusage = fig.add_subplot(211)
    mainswatch = fig.add_subplot(212)
    
    # data that we keep track of, the average watt usage as sent in
    # zero out all the data to start
    avgwattdata = [0] * NUMWATTDATASAMPLES
    # which point in the array we're entering new data
    avgwattdataidx = 0
    
    # The watt subplot
    watt_t = np.arange(0, len(avgwattdata), 1)
    wattusageline, = wattusage.plot(watt_t, avgwattdata)
    wattusage.set_ylabel('Watts')
    wattusage.set_ylim(0, 500)
    
    # the mains voltage and current level subplot
    mains_t = np.arange(0, 18, 1)
    voltagewatchline, = mainswatch.plot(mains_t, [0] * 18,
                                        color='blue')
    mainswatch.set_ylabel('Volts (blue)')
    mainswatch.set_xlabel('Sample #')
    mainswatch.set_ylim(-200, 200)
    # make a second axies for amp data
    mainsampwatcher = mainswatch.twinx()
    ampwatchline, = mainsampwatcher.plot(mains_t,
                                         [0] * 18, color='green')
    mainsampwatcher.set_ylabel('Amps (green)')
    mainsampwatcher.set_ylim(-15, 15)
    
    # and a legend for both of them
    #legend((voltagewatchline, ampwatchline), ('volts', 'amps'))


shists = sensorhistory.SensorHistories(logfile)
print shists


if GRAPHIT:
    timer = wx.Timer(wx.GetApp(), -1)
    timer.Start(500)        # run an in every 'n' milli-seconds
    wx.GetApp().Bind(wx.EVT_TIMER, update_graph)
    plt.show()
else:
    while True:
        update_graph(None)

