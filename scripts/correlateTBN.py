#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Example script that reads in TBN data and runs a cross-correlation on it.  
The results are saved in the FITS IDI format.
"""

import os
import sys
import time
import ephem
import numpy
import getopt
from datetime import datetime, timedelta, tzinfo

from lsl import astro
from lsl.reader.ldp import LWA1DataFile
from lsl.common import stations, metabundle, metabundleADP
from lsl.correlator import fx as fxc
from lsl.writer import fitsidi


class UTC(tzinfo):
    """tzinfo object for UTC time."""
    
    def utcoffset(self, dt):
        return timedelta(0)
        
    def tzname(self, dt):
        return "UTC"
        
    def dst(self, dt):
        return timedelta(0)


def usage(exitCode=None):
    print """correlateTBN.py - cross-correlate data in a TBN file

Usage: correlateTBN.py [OPTIONS] file

Options:
-h, --help             Display this help information
-m, --metadata         Name of SSMIF or metadata tarball file to use for 
                    mappings
-l, --fft-length       Set FFT length (default = 16)
-t, --avg-time         Window to average visibilities in time (seconds; 
                    default = 5 s)
-s, --samples          Number of average visibilities to generate
                    (default = 10)
-o, --offset           Seconds to skip from the beginning of the file
-q, --quiet            Run correlateTBN in silent mode
-a, --all              Correlated all dipoles regardless of their status 
                    (default = no)
-x, --xx               Compute only the XX polarization product (default)
-y, --yy               Compute only the YY polarization product
-2, --two-products     Compute both the XX and YY polarization products
-4, --four-products    Compute all for polariation products:  XX, YY, XY, 
                    and YX.
"""
    
    if exitCode is not None:
        sys.exit(exitCode)
    else:
        return True


def parseConfig(args):
    config = {}
    # Command line flags - default values
    config['metadata'] = ''
    config['avgTime'] = 5.0
    config['LFFT'] = 16
    config['samples'] = 10
    config['offset'] = 0
    config['verbose'] = True
    config['all'] = False
    config['products'] = ['xx',]
    config['args'] = []
    
    # Read in and process the command line flags
    try:
        opts, arg = getopt.getopt(args, "hm:ql:t:s:o:a24xy", ["help", "metadata=", "quiet", "fft-length=", "avg-time=", "samples=", "offset=", "all", "two-products", "four-products", "xx", "yy"])
    except getopt.GetoptError, err:
        # Print help information and exit:
        print str(err) # will print something like "option -a not recognized"
        usage(exitCode=2)
        
    # Work through opts
    for opt, value in opts:
        if opt in ('-h', '--help'):
            usage(exitCode=0)
        elif opt in ('-m', '--metadata'):
            config['metadata'] = value
        elif opt in ('-q', '--quiet'):
            config['verbose'] = False
        elif opt in ('-l', '--fft-length'):
            config['LFFT'] = int(value)
        elif opt in ('-t', '--avg-time'):
            config['avgTime'] = float(value)
        elif opt in ('-s', '--samples'):
            config['samples'] = int(value)
        elif opt in ('-o', '--offset'):
            config['offset'] = int(value)
        elif opt in ('-a', '--all'):
            config['all'] = True
        elif opt in ('-2', '--two-products'):
            config['products'] = ['xx', 'yy']
        elif opt in ('-4', '--four-products'):
            config['products'] = ['xx', 'yy', 'xy', 'yx']
        elif opt in ('-x', '--xx'):
            config['products'] = ['xx',]
        elif opt in ('-y', '--yy'):
            config['products'] = ['yy',]
        else:
            assert False
            
    # Add in arguments
    config['args'] = arg
    
    # Return configuration
    return config


def processChunk(idf, site, good, filename, intTime=5.0, LFFT=64, Overlap=1, pols=['xx',], ChunkSize=100):
    """
    Given a lsl.reader.ldp.TBNFile instances and various parameters for the 
    cross-correlation, write cross-correlate the data and save it to a file.
    """
    
    # Get antennas
    antennas = site.get_antennas()
    
    # Get the metadata
    sample_rate = idf.get_info('sample_rate')
    central_freq = idf.get_info('freq1')
    
    # Create the list of good digitizers and a digitizer to Antenna instance mapping.  
    # These are:
    #  toKeep  -> mapping of digitizer number to array location
    #  mapper -> mapping of Antenna instance to array location
    toKeep = [antennas[i].digitizer-1 for i in good]
    mapper = [antennas[i] for i in good]
    
    # Create a list of unqiue stands to know what style of IDI file to create
    stands = set( [antennas[i].stand.id for i in good] )
    
    # Main loop over the input file to read in the data and organize it.  Several control 
    # variables are defined for this:
    #  refTime -> time (in seconds since the UNIX epoch) for the first data set
    #  setTime -> time (in seconds since the UNIX epoch) for the current data set
    refTime = 0.0
    setTime = 0.0
    wallTime = time.time()
    for s in xrange(ChunkSize):
        try:
            readT, t, data = idf.read(intTime)
        except Exception, e:
            print "Error: %s" % str(e)
            continue
            
        ## Prune out what we don't want
        data = data[toKeep,:]
        
        setTime = t
        if s == 0:
            refTime = setTime
            
        # Setup the set time as a python datetime instance so that it can be easily printed
        setDT = datetime.utcfromtimestamp(setTime)
        setDT.replace(tzinfo=UTC())
        print "Working on set #%i (%.3f seconds after set #1 = %s)" % ((s+1), (setTime-refTime), setDT.strftime("%Y/%m/%d %H:%M:%S.%f"))
        
        # Loop over polarization products
        for pol in pols:
            print "->  %s" % pol
            blList, freq, vis = fxc.FXMaster(data, mapper, LFFT=LFFT, Overlap=Overlap, include_auto=True, verbose=False, sample_rate=sample_rate, central_freq=central_freq, Pol=pol, return_baselines=True, gain_correct=True)
            
            # Select the right range of channels to save
            toUse = numpy.where( (freq>5.0e6) & (freq<93.0e6) )
            toUse = toUse[0]
            
            # If we are in the first polarazation product of the first iteration,  setup
            # the FITS IDI file.
            if s  == 0 and pol == pols[0]:
                pol1, pol2 = fxc.pol_to_pols(pol)
                
                if len(stands) > 255:
                    fits = fitsidi.ExtendedIDI(filename, ref_time=refTime)
                else:
                    fits = fitsidi.IDI(filename, ref_time=refTime)
                fits.set_stokes(pols)
                fits.set_frequency(freq[toUse])
                fits.set_geometry(site, [a for a in mapper if a.pol == pol1])
                
            # Convert the setTime to a MJD and save the visibilities to the FITS IDI file
            obsTime = astro.unix_to_taimjd(setTime)
            fits.add_data_set(obsTime, readT, blList, vis[:,toUse], pol=pol)
        print "->  Cummulative Wall Time: %.3f s (%.3f s per integration)" % ((time.time()-wallTime), (time.time()-wallTime)/(s+1))
        
    # Cleanup after everything is done
    fits.write()
    fits.close()
    del(fits)
    del(data)
    del(vis)
    return True


def main(args):
    # Parse command line options
    config = parseConfig(args)
    filename = config['args'][0]
    
    # Length of the FFT
    LFFT = config['LFFT']
    
    # Setup the LWA station information
    if config['metadata'] != '':
        try:
            station = stations.parse_ssmif(config['metadata'])
        except ValueError:
            try:
                station = metabundle.getStation(config['metadata'], apply_sdm=True)
            except:
                station = metabundleADP.getStation(config['metadata'], apply_sdm=True)
    else:
        station = stations.lwa1
    antennas = station.get_antennas()
    
    idf = LWA1DataFile(filename)
    
    jd = astro.unix_to_utcjd(idf.get_info('tStart'))
    date = str(ephem.Date(jd - astro.DJD_OFFSET))
    nFpO = len(antennas)
    sample_rate = idf.get_info('sample_rate')
    nInts = idf.get_info('nFrames') / nFpO
    
    # Get valid stands for both polarizations
    goodX = []
    goodY = []
    for i in xrange(len(antennas)):
        ant = antennas[i]
        if ant.combined_status != 33 and not config['all']:
            pass
        else:
            if ant.pol == 0:
                goodX.append(ant)
            else:
                goodY.append(ant)
                
    # Now combine both lists to come up with stands that
    # are in both so we can form the cross-polarization 
    # products if we need to
    good = []
    for antX in goodX:
        for antY in goodY:
            if antX.stand.id == antY.stand.id:
                good.append( antX.digitizer-1 )
                good.append( antY.digitizer-1 )
                
    # Report on the valid stands found.  This is a little verbose,
    # but nice to see.
    print "Found %i good stands to use" % (len(good)/2,)
    for i in good:
        print "%3i, %i" % (antennas[i].stand.id, antennas[i].pol)
        
    # Number of frames to read in at once and average
    nFrames = int(config['avgTime']*sample_rate/512)
    config['offset'] = idf.offset(config['offset'])
    nSets = idf.get_info('nFrames') / nFpO / nFrames
    nSets = nSets - int(config['offset']*sample_rate/512) / nFrames
    
    central_freq = idf.get_info('freq1')
    
    print "Data type:  %s" % type(idf)
    print "Samples per observations: %i per pol." % (nFpO/2)
    print "Sampling rate: %i Hz" % sample_rate
    print "Tuning frequency: %.3f Hz" % central_freq
    print "Captures in file: %i (%.1f s)" % (nInts, nInts*512 / sample_rate)
    print "=="
    print "Station: %s" % station.name
    print "Date observed: %s" % date
    print "Julian day: %.5f" % jd
    print "Offset: %.3f s (%i frames)" % (config['offset'], config['offset']*sample_rate/512)
    print "Integration Time: %.3f s" % (512*nFrames/sample_rate)
    print "Number of integrations in file: %i" % nSets
    
    # Make sure we don't try to do too many sets
    if config['samples'] > nSets:
        config['samples'] = nSets
        
    # Loop over junks of 300 integrations to make sure that we don't overflow 
    # the FITS IDI memory buffer
    s = 0
    leftToDo = config['samples']
    basename = os.path.split(filename)[1]
    basename, ext = os.path.splitext(basename)
    while leftToDo > 0:
        fitsFilename = "%s.FITS_%i" % (basename, (s+1),)
        
        if leftToDo > 100:
            chunk = 100
        else:
            chunk = leftToDo
            
        processChunk(idf, station, good, fitsFilename, intTime=config['avgTime'], LFFT=config['LFFT'], 
                    Overlap=1, pols=config['products'], ChunkSize=chunk)
                    
        s += 1
        leftToDo = leftToDo - chunk
        
    idf.close()


if __name__ == "__main__":
    main(sys.argv[1:])
