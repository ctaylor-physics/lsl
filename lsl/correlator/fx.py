#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Python module to handle the channelization and cross-correlation of TBW and
TBN data.  The main functions in this module are:
* calcSpectra - calculate power spectra for a collection of signals
* FXCorrelator - calculate cross power spectra for a collection of signals
Each function is set up to process the signals in parallel using the 
processing module and accepts a variety of options controlling the processing
of the data, including various window functions and time averaging."""

import os
import sys
import math
import numpy

from ..common import dp as dp_common
from ..common.constants import *
import uvUtils

__version__ = '0.2'
__revision__ = '$ Revision: 6 $'
__all__ = ['blackmanWindow', 'sincWindow', 'polyphaseFilter', 'calcSpectrum', 'calcSpectra', 'correlate', 'FXcorrelator', 'tpi' '__version__', '__revision__', '__all__']


def blackmanWindow(length):
	"""Generate a Blackman window of the specified length.  The window is returned
	as a numpy array."""

	N = length - 1
	x = numpy.linspace(0,length-1,length)
	w = 0.42 - 0.50*numpy.cos(2*numpy.pi*x/N) + 0.08*numpy.cos(4*numpy.pi*x/N)

	return w


def sincWindow(length):
	"""Generate a sinc function of length elements such that the function 
	evaluates to zero at both ends of the range. The output is the sinc function
	as a numpy array."""

	x = numpy.arange(length)
	xPrime = 4*math.pi/float(length)*(x-length/2)
	fnc = numpy.sin(xPrime)/xPrime

	# Fix "the z=0 problem"
	z = numpy.where( xPrime == 0 )
	if len(z[0]) != 0:
		fnc[z[0]] = 1.0

	return fnc


def polyphaseFilter(signal, length=64, windows=4):
	"""Polyphase filter for the time series data.  This function multiplies the 
	input signal by a sinc function, breaks it into windows, and sum over the 
	different windows.  This results in a decimation of the signal by a factor 
	proportional to the number of windows used.  The output is the decimated 
	signal as a numpy array."""
	
	# The averaging length holds the size of the signal to be filtered
	aLength = length*windows
	filtered = numpy.zeros(signal.shape[0]/length/windows*length)

	# Loop over the signal
	for i in range(signal.shape[0]/aLength):
		# Current section of length 'length'
		s1 = signal[aLength*i:aLength*(i+1)]
		s1 = s1*sincWindow(aLength)

		# Create the 'windows' window components out of the sinc-multiplied signal
		parts = numpy.zeros((windows, length))
		for j in range(parts.shape[0]):
			parts[j,:] = s1[length*j:length*(j+1)]

		# Sum and save to the output array
		filtered[length*i:length*(i+1)] = parts.sum(axis=0)

	return filtered


def calcSpectrum(signal, LFFT=64, BlackmanFilter=False, PolyphaseFilter=False, verbose=False):
	"""Worker function for calcSpectra."""

	# Figure out if we are working with complex (I/Q) data or only real.  This
	# will determine how the FFTs are done since the real data mirrors the pos-
	# itive and negative Fourier frequencies.
	if signal.dtype.kind == 'c':
		lFactor = 1
	else:
		lFactor = 2

	out = numpy.zeros(LFFT-1)

	# Optionally apply a polyphase filter to the signals and store the results in
	# is intermediate signal variables 'is[12]'
	if PolyphaseFilter:
		intSignal = polyphaseFilter(signal, length=2*LFFT, windows=4)
		if verbose:
			print "  %i samples -> %i filtered samples" % (signal.shape[0], intSignal.shape[0])
	else:
		intSignal = signal

	# Remove the mean
	intSignal -= intSignal.mean()

	nChunks = intSignal.shape[0]/lFactor/LFFT
	if verbose:
		print "  %i samples -> %i chunks" % (intSignal.shape[0], nChunks)

	for i in range(nChunks):
		cs = intSignal[i*lFactor*LFFT:(i+1)*lFactor*LFFT]
		if BlackmanFilter:
			cs *= blackmanWindow(lFactor*LFFT)
		cf = numpy.fft.fft(cs, lFactor*LFFT)
		cp = numpy.abs(cf)**2.0
			
		out += cp[1:LFFT]
	out /= float(nChunks)

	return out


def calcSpectra(signals, LFFT=64, SampleAverage=None, BlackmanFilter=False, PolyphaseFilter=False, DisablePool=False, verbose=False, SampleRate=None, CentralFreq=0.0):
	"""Given a collection of time series data with inputs on the first dimension
	and data on the second, compute the spectra for all inputs.  By default, 
	all data in the time series are average into a single spectrum.  However, this 
	behavior can be modified if the SampleAverage keyword is set.  SampleAverage 
	specifies how many individual spectra of length LFFT are to be averaged."""

	# Figure out if we are working with complex (I/Q) data or only real.  This
	# will determine how the FFTs are done since the real data mirrors the pos-
	# itive and negative Fourier frequencies.
	if signals.dtype.kind == 'c':
		lFactor = 1
		doFFTShift = True
		CentralFreq = float(CentralFreq)
	else:
		lFactor = 2
		doFFTShift = False

	# Calculate the frequencies of the FFTs.  We do this for twice the FFT length
	# because the real-valued signal only occupies the positive part of the 
	# frequency space.
	if SampleRate is None:
		SampleRate = dp_common.fS
	freq = numpy.fft.fftfreq(lFactor*LFFT, d=1.0/SampleRate)
	# Deal with TBW and TBN data in the correct way
	if doFFTShift:
		freq += CentralFreq
		freq = numpy.fft.fftshift(freq)
	freq = freq[1:LFFT]

	# Calculate the number of output bins with respect to time.  If SampleAverage 
	# is None, average up everything.
	if SampleAverage is None:
		SampleAverage = signals.shape[1] / lFactor / LFFT
	nSamples = signals.shape[1] / lFactor / LFFT / int(SampleAverage)

	# The processing module allows for the creation of worker pools to help speed
	# things along.  If the processing module is found, use it.  Otherwise, set
	# the 'usePool' variable to false and run single threaded.
	try:
		from processing import Pool
		
		# To get results pack from the pool, you need to keep up with the workers.  
		# In addition, we need to keep up with which workers goes with which 
		# signal since the workers are called asychronisly.  Thus, we need a 
		# taskList array to hold tuples of signal ('count') and workers.
		taskPool = Pool(processes=6)
		taskList = []

		usePool = True
	except ImportError:
		usePool = False
	
	# Turn off the thread pool if we are explicitly told not to use it.
	if DisablePool:
		usePool = False

	output = numpy.zeros( (signals.shape[0], nSamples, freq.shape[0]) )
	for i in range(signals.shape[0]):
		for j in range(nSamples):
			# Figure out which section of each signal to average
			bchan = j*lFactor*LFFT*SampleAverage
			echan = (j+1)*lFactor*LFFT*SampleAverage
			if echan >= signals.shape[1]:
				echan = -1

			if verbose:
				print "Working on signal %i of %i, section %i to %i" % (i+1, signals.shape[0], bchan, echan)

			# If pool, pool...  Otherise don't
			if usePool:
				task = taskPool.apply_async(calcSpectrum, args=(signals[i,bchan:echan], ), 
									kwds={'LFFT': LFFT, 'BlackmanFilter': BlackmanFilter, 'PolyphaseFilter': PolyphaseFilter, 'verbose': verbose})
				taskList.append((i,j,task))
			else:
				tempPS = calcSpectrum(signals[i,bchan:echan], LFFT=LFFT, BlackmanFilter=BlackmanFilter, PolyphaseFilter=PolyphaseFilter, verbose=verbose)

				if doFFTShift:
					output[i,j,:] = numpy.fft.fftshift(tempPS)
				else:
					output[i,j,:] = tempPS

	# If pooling... Close the pool so that it knows that no ones else is joining.  
	# Then, join the workers together and wait on the last one to finish before 
	# saving the results.
	if usePool:
		taskPool.close()
		taskPool.join()

		# This is where he taskList list comes in handy.  We now know who did what
		# when we unpack the various results
		for i,j,task in taskList:
			if doFFTShift:
				output[i,j,:] = numpy.fft.fftshift(task.get())
			else:
				output[i,j,:] = task.get()

		# Destroy the taskPool
		del(taskPool)

	# Trim single dimensions from the output if they are found.  This is the 
	# default behavior
	output = numpy.squeeze(output)

	return (freq, output)


def correlate(signal1, signal2, stand1, stand2, LFFT=64, Overlap=1, BlackmanFilter=False, PolyphaseFilter=False, verbose=False, SampleRate=None, DlyCache=None, CentralFreq=0.0):
	"""Channalize and cross-correlate singal from two antennae.  Both the signals 
	and the stand numnbers are needed to implement time delay and phase corrections.
	The resulting visibilities from the cross-correlation are time average and a 
	LFFT-1 length numpy array is returned.  This array does not contain the DC 
	component of the signal."""

	import aipy

	# Figure out if we are working with complex (I/Q) data or only real.  This
	# will determine how the FFTs are done since the real data mirrors the pos-
	# itive and negative Fourier frequencies.
	if signal1.dtype.kind == 'c':
		lFactor = 1
		doFFTShift = True
		CentralFreq = float(CentralFreq)
	else:
		lFactor = 2
		doFFTShift = False

	# Calculate the frequencies of the FFTs.  We do this for twice the FFT length
	# because the real-valued signal only occupies the positive part of the 
	# frequency space.
	if SampleRate is None:
		SampleRate = dp_common.fS
	freq = numpy.fft.fftfreq(lFactor*LFFT, d=1.0/SampleRate)
	# Deal with TBW and TBN data in the correct way
	if doFFTShift:
		freq += CentralFreq
		freq = numpy.fft.fftshift(freq)
	freq = freq[1:LFFT]
	delayRef = len(freq)/2

	DlyCache.updateFreq(freq)

	# Calculate the frequency-based cable delays in seconds.
	if DlyCache is None:
		delay1 = uvUtils.signalDelay(stand1, freq=freq)
		delay2 = uvUtils.signalDelay(stand2, freq=freq)
	else:
		delay1 = DlyCache.signalDelay(stand1)
		delay2 = DlyCache.signalDelay(stand2)

	if delay2[delayRef] > delay1[delayRef]:
		delay1 = delay2 - delay1
		delay2 = delay2 - delay2
	else:
		delay2 = delay1 - delay2 
		delay1 = delay1 - delay1

	start1 = int(round(delay1[delayRef]*SampleRate))
	start2 = int(round(delay2[delayRef]*SampleRate))

	if verbose:
		print "  Delay for stands #%i: %.2f - %.2f ns (= %i samples)" % (stand1, delay1[-1]*1e9, delay1[0]*1e9, start1)
		print "  Delay for stands #%i: %.2f - %.2f ns (= %i samples)" % (stand2, delay2[-1]*1e9, delay2[0]*1e9, start2)

	# Optionally apply a polyphase filter to the signals and store the results in
	# is intermediate signal variables 'is[12]'
	if PolyphaseFilter:
		is1 = polyphaseFilter(signal1, length=lFactor*LFFT, windows=4)
		is2 = polyphaseFilter(signal2, length=lFactor*LFFT, windows=4)
	else:
		is1 = 1.0*signal1
		is2 = 1.0*signal2

	# Remove the mean
	is1 -= is1.mean()
	is2 -= is2.mean()

	# Compute the length of each time series and find the shortest one.
	length1 = (is1.shape[0] - start1) / LFFT / lFactor
	length2 = (is2.shape[0] - start2) / LFFT / lFactor
	# Factor in  the overlap amount for all but the last full sample
	length = numpy.array([length1, length2]).min() * Overlap - Overlap + 1

	# Begin computing the visibilities and loop over the signal chuncks in order 
	# to average in time.
	visibility = numpy.zeros(LFFT-1, dtype=numpy.complex_)
	for i in range(length):
		# Current chunks
		s1 = is1[(start1+int(lFactor*LFFT*(1.0*i)/Overlap)):(start1+int(lFactor*LFFT*((1.0*i)/Overlap+1)))]
		s2 = is2[(start2+int(lFactor*LFFT*(1.0*i)/Overlap)):(start2+int(lFactor*LFFT*((1.0*i)/Overlap+1)))]
		#import pylab
		#pylab.plot(s1.real)
		#pylab.plot(s2.real)
		#pylab.show()

		if BlackmanFilter:
			s1 *= blackmanWindow(lFactor*LFFT)
			s2 *= blackmanWindow(lFactor*LFFT)
		
		# The FFTs
		fft1 = numpy.fft.fft(s1, lFactor*LFFT)
		fft2 = numpy.fft.fft(s2, lFactor*LFFT)
		
		if doFFTShift:
			fft1 = numpy.fft.fftshift(fft1)
			fft2 = numpy.fft.fftshift(fft2)

		# Calculate the visibility of the desired part of the frequency space
		tempVis = fft2[1:LFFT]*(fft1[1:LFFT].conj())

		# Add it on to the master output visibility for averaging
		visibility += tempVis
	
	# Apply the phase rotator to the visibility
	#visibility *= numpy.exp(2j*numpy.pi*freq*((delay1-start1/SampleRate)-(delay2-start2/SampleRate)))

	# Average and return
	visibility /= float(length)

	return visibility


def FXCorrelator(signals, stands, LFFT=64, Overlap=1, IncludeAuto=False, BlackmanFilter=False, PolyphaseFilter=False, CrossPol=None, DisablePool=False, verbose=False, SampleRate=None, CentralFreq=0.0):
	"""A basic FX correlators for the TBW data.  Given an 2-D array of signals
	(stands, time-series) and an array of stands, compute the cross-correlation of
	the data for all baselines.  If cross-polarizations need to be calculated, the
	CrossPol keyword allows for the other polarization data to be entered into the
	correlator.  Return the frequencies and visibilities as a two-elements tuple."""

	N = stands.shape[0]
	baselines = uvUtils.getBaselines(stands, IncludeAuto=IncludeAuto, Indicies=True)
	Nbase = len(baselines)
	output = numpy.zeros( (Nbase, LFFT-1), dtype=numpy.complex64)

	# Figure out if we are working with complex (I/Q) data or only real.  This
	# will determine how the FFTs are done since the real data mirrors the pos-
	# itive and negative Fourier frequencies.
	if signals.dtype.kind == 'c':
		lFactor = 1
		doFFTShift = True
		CentralFreq = float(CentralFreq)
	else:
		lFactor = 2
		doFFTShift = False

	if SampleRate is None:
		SampleRate = dp_common.fS
	freq = numpy.fft.fftfreq(lFactor*LFFT, d=1.0/SampleRate)
	if doFFTShift:
		freq += CentralFreq
		freq = numpy.fft.fftshift(freq)
	freq = freq[1:LFFT]

	# Define the cable/signal delay caches to help correlate along
	dlyCache = uvUtils.SignalCache(freq)

	# The processing module allows for the creation of worker pools to help speed
	# things along.  If the processing module is found, use it.  Otherwise, set
	# the 'usePool' variable to false and run single threaded.
	try:
		from processing import Pool
		
		# To get results pack from the pool, you need to keep up with the workers.  
		# In addition, we need to keep up with which workers goes with which 
		# baseline since the workers are called asychronisly.  Thus, we need a 
		# taskList array to hold tuples of baseline ('count') and workers.
		taskPool = Pool(processes=4)
		taskList = []

		usePool = True
	except ImportError:
		usePool = False

	# Turn off the thread pool if we are explicitly told not to use it.
	if DisablePool:
		usePool = False

	# Loop over baselines
	count = 0
	for i,j in baselines:
		if verbose:
			if i == j:
				print "Auto-correlating stand %i" % stands[i]
			else:
				print "Cross-correlating stands %i and %i" % (stands[i], stands[j])
			
		# If pool, pool...  Otherise don't
		if usePool:
			if CrossPol is not None:
				task = taskPool.apply_async(correlate, args=(signals[i,:], CrossPol[j,:], stands[i], stands[j]), 
								kwds={'LFFT': LFFT, 'Overlap': Overlap, 'BlackmanFilter': BlackmanFilter, 'PolyphaseFilter': PolyphaseFilter, 'verbose': verbose, 'SampleRate': SampleRate, 'DlyCache': dlyCache, 'CentralFreq': CentralFreq})
			else:
				task = taskPool.apply_async(correlate, args=(signals[i,:], signals[j,:], stands[i], stands[j]), 
								kwds={'LFFT': LFFT, 'Overlap': Overlap, 'BlackmanFilter': BlackmanFilter, 'PolyphaseFilter': PolyphaseFilter, 'verbose': verbose, 'SampleRate': SampleRate, 'DlyCache': dlyCache, 'CentralFreq': CentralFreq})
			taskList.append((count,task))
		else:
			if CrossPol is not None:
				tempCPS = correlate(signals[i,:], CrossPol[j,:], stands[i], stands[j], LFFT=LFFT, Overlap=Overlap, BlackmanFilter=BlackmanFilter, PolyphaseFilter=PolyphaseFilter, verbose=verbose, SampleRate=SampleRate, DlyCache=dlyCache, CentralFreq=CentralFreq)
			else:
				tempCPS = correlate(signals[i,:], signals[j,:], stands[i], stands[j], LFFT=LFFT, Overlap=Overlap, BlackmanFilter=BlackmanFilter,  PolyphaseFilter=PolyphaseFilter, verbose=verbose, SampleRate=SampleRate, DlyCache=dlyCache, CentralFreq=CentralFreq)

			if doFFTShift:
				output[count,:] = tempCPS
			else:
				output[count,:] = tempCPS
		count = count + 1

	# If pooling... Close the pool so that it knows that no ones else is joining.  
	# Then, join the workers together and wait on the last one to finish before 
	# saving the results.
	if usePool:
		taskPool.close()
		taskPool.join()

		# This is where he taskList list comes in handy.  We now know who did what
		# when we unpack the various results
		for count,task in taskList:
			if doFFTShift:
				output[count,:] = task.get()
			else:
				output[count,:] = task.get()

		# Destroy the taskPool
		del(taskPool)

	return (freq, output)


if __name__ == "__main__":
	import aipy
	import robust

	import matplotlib.pyplot as plt
	from matplotlib.ticker import NullFormatter

	# Pre 8/25/10
	#stands = numpy.array([214, 212, 228, 204, 225, 210, 187, 174, 123, 125])
	# Post 8/25/10
	stands = numpy.array([214, 212, 228, 206, 127, 157, 187, 208, 123, 125])

	from readTBW import *
	from readerErrors import *

	#fh = open("/home/jdowell/055424_740_threeTBW.dat", "rb")
	#fh = open("/home/jdowell/triple12M_TBW_Midnight_Sept_3.dat", "rb")
	#fh = open("/home/jdowell/12M_TBW_430pm_Sept_8.dat", "rb")
	fh = open("/home/jdowell/12M_TBW_900pm_Sept_8.dat", "rb")
	jd = 2455448.62500
	#fh = open("/home/jdowell/tbw_test1_091310.dat", "rb")
	#jd = 2455453.31531
	nSamples = 300000

	refTime = 0.0
	setTime = 0.0

	for s in range(1):
		count = {}
		masterCount = 0
		iTime = 0
		data = numpy.zeros((20,12000000), dtype=numpy.int16)
		for i in range(nSamples):
			# Read in the next frame and anticipate any problems that could occur
			try:
				cFrame = readTBWFrame(fh, Verbose=False)
			except eofError:
				break
			except syncError:
				print "WARNING: Mark 5C sync error on frame #%i" % (int(fh.tell())/TBWFrameSize-1)
				continue
			except numpyError:
				break

			stand = cFrame.header.parseID()
			if i == 0:
				if s == 0:
					refTime = cFrame.header.secondsCount
				setTime = cFrame.header.secondsCount
			print "%2i  %6.3f  %5i  %5i" % (stand, cFrame.getTime(), cFrame.header.frameCount, cFrame.header.secondsCount)
			if stand not in count.keys():
				count[stand] = 0

			if stand < 11:
				if cFrame.getDataBits() == 12:
					data[2*(stand-1),  count[stand]*400:(count[stand]+1)*400] = numpy.squeeze(cFrame.data.xy[0,:])
					data[2*(stand-1)+1,count[stand]*400:(count[stand]+1)*400] = numpy.squeeze(cFrame.data.xy[1,:])
				else:
					data[2*(stand-1),  count[stand]*1200:(count[stand]+1)*1200] = numpy.squeeze(cFrame.data.xy[0,:])
					data[2*(stand-1)+1,count[stand]*1200:(count[stand]+1)*1200] = numpy.squeeze(cFrame.data.xy[1,:])

			count[stand] = count[stand] + 1
			masterCount = masterCount + 1

		LFFT = 64
		freqY, specY = calcSpectra(data[0::2,:], LFFT=LFFT, PolyphaseFilter=True, verbose=True)
		freqX, specX = calcSpectra(data[1::2,:], LFFT=LFFT, PolyphaseFilter=True, verbose=True)

		rfiClip = 5

		rfiX = {}
		bandpassX = {}
		rfiY = {}
		bandpassY = {}

		valid = numpy.where( (freqX>20.0e6) & (freqX<88.0e6) )
		valid = valid[0]
		for i in range(specX.shape[0]):
			sm = robust.robustMean(specX[i,valid])
			ss = robust.robustSigma(specX[i,valid])

			rfiX[i] = freqX[valid[numpy.where( specX[i,valid] > sm+rfiClip*ss )]]
			bandpassX[i] = numpy.zeros_like(valid)*sm

		valid = numpy.where( (freqY>20.0e6) & (freqY<88.0e6) )
		valid = valid[0]
		for i in range(specY.shape[0]):
			sm = robust.robustMean(specY[i,valid])
			ss = robust.robustSigma(specY[i,valid])
			
			rfiY[i] = freqY[valid[numpy.where( specY[i,valid] > sm+rfiClip*ss )]]
			bandpassY[i] = numpy.zeros_like(valid)*sm

		print "Working on set #%i (%i seconds after set #1)" % ((s+1), (setTime-refTime))
		freqYY, outYY = FXCorrelator(data[0::2,:], stands, LFFT=LFFT, PolyphaseFilter=True, verbose=True)
		freqXX, outXX = FXCorrelator(data[1::2,:], stands, LFFT=LFFT, PolyphaseFilter=True, verbose=True)
		freqYX, outYX = FXCorrelator(data[0::2,:], stands, LFFT=LFFT, PolyphaseFilter=True, verbose=True, CrossPol=data[1::2,:])
		freqXY, outXY = FXCorrelator(data[1::2,:], stands, LFFT=LFFT, PolyphaseFilter=True, verbose=True, CrossPol=data[0::2,:])
		uvw = uvUtils.computeUVW(stands, HA=((setTime-refTime)/3600.0), freq=freqXX)
		ccList = uvUtils.getBaselines(stands, Indicies=True)

		toUse = numpy.where( (freqYY>20.0e6) & (freqYY<88.0e6) )
		toUse = toUse[0]

		if s == 0:
			uv = aipy.miriad.UV('test-20100908-2100.uv', status='new')
			tags = ['nants', 'nchan', 'npol', 'pol', 'sfreq', 'sdf', 'longitu', 'latitud', 'dec', 'ra', 'source']
			codes = ['i', 'i', 'i', 'i', 'r', 'r', 'r', 'r', 'r', 'r', 'a']
			for tag,code in zip(tags, codes):
				print "%s -> %s" % (tag, code)
				uv.add_var(tag, code)
			uv['source'] = 'zenith'
			uv['longitu'] = -107.628
			uv['latitud'] = 34.070
			uv['dec'] = 34.070
			uv['nants'] = stands.shape[0]
			uv['nchan'] = toUse.shape[0]
			uv['npol'] = 4
			uv['sfreq'] = freqYY[toUse[0]]
			uv['sdf'] = freqYY[toUse[1]]-freqYY[toUse[0]]

		uv['pol'] = -6
		for i in range(uvw.shape[0]):
			preamble = (numpy.squeeze(uvw[i,:,toUse[0]]), jd+(setTime-refTime)/3600.0/24.0, ccList[i])

			current = numpy.squeeze( outYY[i,toUse] )
			#current = current / bandpassY[ccList[i][0]] / bandpassY[ccList[i][1]]

			mask = numpy.zeros_like(current)
			for cf in rfiY[ccList[i][0]]:
				bad = numpy.where( cf == freqYY[toUse] )
				if len(bad[0]) != 0:
					mask[bad] = 1
			for cf in rfiY[ccList[i][1]]:
				bad = numpy.where( cf == freqYY[toUse] )
				if len(bad[0]) != 0:
					mask[bad] = 1

			uv.write(preamble, current, mask)

		uv['pol'] = -5
		for i in range(uvw.shape[0]):
			preamble = (numpy.squeeze(uvw[i,:,toUse[0]]), jd+(setTime-refTime)/3600.0/24.0, ccList[i])

			current = numpy.squeeze( outXX[i,toUse] )
			#current = current / bandpassX[ccList[i][0]] / bandpassX[ccList[i][1]]

			mask = numpy.zeros_like(current)
			for cf in rfiX[ccList[i][0]]:
				bad = numpy.where( cf == freqXX[toUse] )
				if len(bad[0]) != 0:
					mask[bad] = 1
			for cf in rfiX[ccList[i][1]]:
				bad = numpy.where( cf == freqXX[toUse] )
				if len(bad[0]) != 0:
					mask[bad] = 1

			uv.write(preamble, current, mask)

		uv['pol'] = -8
		for i in range(uvw.shape[0]):
			preamble = (numpy.squeeze(uvw[i,:,toUse[0]]), jd+(setTime-refTime)/3600.0/24.0, ccList[i])

			current = numpy.squeeze( outYX[i,toUse] )
			#current = current / bandpassY[ccList[i][0]] / bandpassX[ccList[i][1]]

			mask = numpy.zeros_like(current)
			for cf in rfiY[ccList[i][0]]:
				bad = numpy.where( cf == freqYY[toUse] )
				if len(bad[0]) != 0:
					mask[bad] = 1
			for cf in rfiX[ccList[i][1]]:
				bad = numpy.where( cf == freqXX[toUse] )
				if len(bad[0]) != 0:
					mask[bad] = 1

			uv.write(preamble, current, mask)

		uv['pol'] = -7
		for i in range(uvw.shape[0]):
			preamble = (numpy.squeeze(uvw[i,:,toUse[0]]), jd+(setTime-refTime)/3600.0/24.0, ccList[i])

			current = numpy.squeeze( outXY[i,toUse] )
			#current = current / bandpassX[ccList[i][0]] / bandpassY[ccList[i][1]]

			mask = numpy.zeros_like(current)
			for cf in rfiX[ccList[i][0]]:
				bad = numpy.where( cf == freqXX[toUse] )
				if len(bad[0]) != 0:
					mask[bad] = 1
			for cf in rfiY[ccList[i][1]]:
				bad = numpy.where( cf == freqYY[toUse] )
				if len(bad[0]) != 0:
					mask[bad] = 1

			uv.write(preamble, current, mask)

		del(data)

	fh.close()
	