#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import getopt
from datetime import datetime, timedelta

from lsl.common.mcs import mjdmpm2datetime, mode2string
from lsl.common import metabundle
from lsl.reader import tbw,tbn,drx,errors


def obsComp(x, y):
	"""
	Function to help sort observations in time.
	"""
	
	tX = mjdmpm2datetime(x['MJD'], x['MPM'])
	tY = mjdmpm2datetime(y['MJD'], y['MPM'])
	if tX < tY:
		return -1
	elif tX > tY:
		return 1
	else:
		return 0


def usage(exitCode=None):
	print """splitSession.py - Given a MCS metadata tarball and a session data file, 
split the data file into individual observations.

Usage:
splitSession.py [OPTIONS] MetaData DataFile

Options:
-h, --help             Display this help information
"""

	if exitCode is not None:
		sys.exit(exitCode)
	else:
		return True


def parseConfig(args):
	config = {}
	# Command line flags - default values

	# Read in and process the command line flags
	try:
		opts, arg = getopt.getopt(args, "h", ["help",])
	except getopt.GetoptError, err:
		# Print help information and exit:
		print str(err) # will print something like "option -a not recognized"
		usage(exitCode=2)
	
	# Work through opts
	for opt, value in opts:
		if opt in ('-h', '--help'):
			usage(exitCode=0)
		else:
			assert False
			
	# Add in arguments
	config['args'] = arg
	
	# Validate
	if len(config['args']) < 2:
		raise RuntimeError("Must specify both a metadata and data file")

	# Return configuration
	return config


def main(args):
	# Get the file names
	config = parseConfig(args)
	
	meta = config['args'][0]
	data = config['args'][1]

	# Get all observations and their start times
	sdf = metabundle.getSessionDefinition(meta)
	ses = metabundle.getSessionSpec(meta)
	obs = metabundle.getObservationSpec(meta)
	obs.sort(obsComp)
	tStart = []
	oDetails = []
	for i,o in enumerate(obs):
		tStart.append( mjdmpm2datetime(o['MJD'], o['MPM']) )
		oDetails.append( {'m': o['Mode'], 'd': o['Dur'] / 1000.0, 'f': o['BW'], 
				  'p': o['projectID'], 's': o['sessionID'], 'o': o['obsID'], 't': sdf.sessions[0].observations[o['obsID']-1].target} )

		print "Observation #%i" % (o['obsID'])
		print " Start: %i, %i -> %s" % (o['MJD'], o['MPM'], tStart[-1])
		print " Mode: %s" % mode2string(o['Mode'])
		print " BW: %i" % o['BW']
		print " Target: %s" % sdf.sessions[0].observations[o['obsID']-1].target
	print " "

	# Figure out where in the file the various bits are.
	fh = open(data, 'rb')
	lf = drx.readFrame(fh)
	beam, j, k = lf.parseID()
	if beam != obs[0]['drxBeam']:
		print 'ERROR: Beam mis-match, metadata is for #%i, file is for #%i' % (obs[0]['drxBeam'], beam)
		sys.exit()
	firstFrame = datetime.utcfromtimestamp(lf.getTime())
	if abs(firstFrame - min(tStart)) > timedelta(seconds=30):
		print 'ERROR: Time mis-match, metadata is for %s, file is for %s' % (min(tStart), firstFrame)
		sys.exit()
	fh.seek(0)

	for i in xrange(len(tStart)):
		eof = False

		## Get observation properties
		oStart = tStart[i]
		oMode = mode2string(oDetails[i]['m'])
		oDur  = oDetails[i]['d']
		oBW   = oDetails[i]['f']
		print "Seeking %s observation of %.3f seconds at %s" % (oMode, oDur, oStart)

		## Get the correct reader to use
		if oMode == 'TBW':
			reader = tbw
			bwKey = None
			bwMult = 520.0 / 400
			fCount = 400
		elif oMode == 'TBN':
			reader = tbn
			bwKey = tbn.filterCodes
			bwMult = 520.0 / 512
			fCount = 512
		else:
			reader = drx
			bwKey = drx.filterCodes
			bwMult = 4.0 / 4096
			fCount = 4096

		## Jump ahead to where the next frame should be, if needed
		if i != 0:
			pDur  = oDetails[i-1]['d']
			pBW   = oDetails[i-1]['f']

			nFramesSkip = int(pDur*bwKey[pBW]*bwMult)
			fh.seek(nFramesSkip*reader.FrameSize, 1)
			if fh.tell() >= os.path.getsize(data):
				print "At file's end"
				fh.seek(-10*reader.FrameSize, 2)
			

		## Figure out where we are and make sure we line up on a frame
		## NOTE: This should never be needed
		fail = True
		while fail:
			try:
				frame = reader.readFrame(fh)
				fail = False
			except errors.syncError:
				fh.seek(1, 1)
			except errors.eofError:
				break
		fh.seek(-reader.FrameSize, 1)	

		## Go in search of the start of the observation
		if datetime.utcfromtimestamp(frame.getTime()) < oStart:
			### We aren't at the beginning yet, seek fowards
			print "-> At byte %i, time is %s < %s" % (fh.tell(), datetime.utcfromtimestamp(frame.getTime()), oStart)

			while datetime.utcfromtimestamp(frame.getTime()) < oStart:
				try:
					frame = reader.readFrame(fh)
				except errors.syncError:		
					fh.seek(1, 1)
				#except errors.eofError:
				#	break
				#print datetime.utcfromtimestamp(frame.getTime()), oStart

		elif datetime.utcfromtimestamp(frame.getTime()) > oStart:
			### We've gone too far, seek backwards
			print "-> At byte %i, time is %s > %s" % (fh.tell(), datetime.utcfromtimestamp(frame.getTime()), oStart)

			while datetime.utcfromtimestamp(frame.getTime()) > oStart:
				if fh.tell() == 0:
					break
				fh.seek(-2*reader.FrameSize, 1)
				try:
					frame = reader.readFrame(fh)
				except errors.syncError:		
					fh.seek(-1, 1)
				except errors.eofError:
					break
				#print datetime.utcfromtimestamp(frame.getTime()), oStart
				
		else:
			### We're there already
			print "-> At byte %i, time is %s = %s" % (fh.tell(), datetime.utcfromtimestamp(frame.getTime()), oStart)

		## Jump back exactly one frame so that the filehandle is in a position 
		## to read the first frame that is part of the observation
		frame = reader.readFrame(fh)
		print "-> At byte %i, time is %s = %s" % (fh.tell(), datetime.utcfromtimestamp(frame.getTime()), oStart)
		fh.seek(-reader.FrameSize, 1)
		
		## Update the bytes ranges
		if fh.tell() < os.path.getsize(data):
			oDetails[i]['b'] = fh.tell()
			oDetails[i]['e'] = -1
		else:
			oDetails[i]['b'] = -1
			oDetails[i]['e'] = -1

		if i != 0:
			oDetails[i-1]['e'] = fh.tell()

		## Progress report
		print '-> Obs.', oDetails[i]['o'], 'starts at byte', oDetails[i]['b']
	print " "

	# Report
	for i in xrange(len(tStart)):
		if oDetails[i]['b'] < 0:
			print "%s, Session %i, Observation %i: not found" % (oDetails[i]['p'], oDetails[i]['s'], oDetails[i]['o'])

		else:
			print "%s, Session %i, Observation %i: %i to %i (%i bytes)" % (oDetails[i]['p'], oDetails[i]['s'], oDetails[i]['o'], oDetails[i]['b'], oDetails[i]['e'], (oDetails[i]['e'] - oDetails[i]['b']))
	print " "

	# Split
	for i in xrange(len(tStart)):
		if oDetails[i]['b'] < 0:
			continue
		outname = '%s_%i_%i_%s.dat' % (oDetails[i]['p'], oDetails[i]['s'], oDetails[i]['o'], oDetails[i]['t'].replace(' ', ''))
		oMode = mode2string(oDetails[i]['m'])

		## Get the correct reader to use
		if oMode == 'TBW':
			reader = tbw

		elif oMode == 'TBN':
			reader = tbn
		else:
			reader = drx

		## Get the number of frames
		if oDetails[i]['e'] > 0:
			nFramesRead = (oDetails[i]['e'] - oDetails[i]['b']) / reader.FrameSize
		else:
			nFramesRead = (os.path.getsize(data) - oDetails[i]['b']) / reader.FrameSize

		## Split
		oh = open(outname, 'wb')
		fh.seek(oDetails[i]['b'])
		for sl in [2**i for i in range(17)[::-1]]:
			while nFramesRead >= sl:
				temp = fh.read(sl*reader.FrameSize)
				oh.write(temp)
				nFramesRead -= sl
		oh.close()
	
	
if __name__ == "__main__":
	main(sys.argv[1:])
	