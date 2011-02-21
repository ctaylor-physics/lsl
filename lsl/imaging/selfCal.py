# -*- coding: utf-8 -*-

"""Simple self-calibration module for correlated TBW and TBN data.

.. versionadded:: 0.4.0
"""

import sys
import math
import numpy

from lsl.sim.vis import scaleData

__version__ = "0.1"
__revision__ = "$ Revision: 1 $"
__all__ = ['selfCal', 'selfCal2', '__version__', '__revision__', '__all__']


def __residualsSCP(delays, amps, dataDict, simDict, chan, pol='yy', MapSize=30, MapRes=0.50):
	"""Private function used to perform a phase self-calibration of data stored 
	in a readUVData dictionary and a model sky stored in a lsl.sim.vis.buildSimSky 
	dictionary.  This function returns the residuals between a scaled and delayed 
	data set and the model sky.  Only the delays are allowed to be updated by 
	scipy.optimize.leastsq in this function."""

	fq = dataDict['freq'][chan] / 1e9
	# Scale and delay the observed visibility data according to the 'delays' and 
	# 'amps' inputs
	scaledVis = []
	for obsVis,(i,j) in zip(dataDict['vis'][pol],dataDict['bls'][pol]):
		scaledVis.append( numpy.array([obsVis[chan]*amps[i]*amps[j]*numpy.exp(-2j*math.pi*fq*(delays[j]-delays[i]))]) )
	obsVis = numpy.concatenate(scaledVis)

	# Mask the simulated sky visibility data with the actual data mask if needed.
	if not simDict['isMasked']:
		maskedVis = []
		for simVis,mask in zip(simDict['vis'][pol], dataDict['msk'][pol]):
			maskedVis.append( simVis.compress(numpy.logical_not(mask)) )
		simVis = numpy.concatenate(maskedVis)
	else:
		maskedVis = []
		for simVis in simDict['vis'][pol]:
			maskedVis.append( numpy.array([simVis[chan]]) )
		simVis = numpy.concatenate(maskedVis)

	# Compute the difference of the two sets of visibilities and return the 
	err = numpy.angle( simVis / obsVis )
	errOut = numpy.where( numpy.abs(err) < numpy.pi, err, numpy.pi-err )
	#print err.max(), errOut.max(), errOut.mean()
	
	return (errOut**2).sum()


def __residualsSCA(amps, delays, dataDict, simDict, chan, pol='yy', MapSize=30, MapRes=0.50):
	"""Private function used to perform a phase self-calibration of data stored in a 
	readUVData dictionary and a model sky stored in a lsl.sim.vis.buildSimSky dictionary.
	This function returns the residuals between a scaled and delayed data set and the 
	model sky.  This function is the counterpart ot residualsSCP and only the gains are 
	allowed to be updated by scipy.optimize.leastsq in this function."""

	fq = dataDict['freq'][chan] / 1e9
	# Scale and delay the observed visibility data according to the 'delays' and 
	# 'amps' inputs
	scaledVis = []
	for obsVis,(i,j) in zip(dataDict['vis'][pol],dataDict['bls'][pol]):
		scaledVis.append( numpy.array([obsVis[chan]*amps[i]*amps[j]*numpy.exp(-2j*math.pi*fq*(delays[j]-delays[i]))]) )
	obsVis = numpy.concatenate(scaledVis)

	# Mask the simulated sky visibility data with the actual data mask if needed.
	if not simDict['isMasked']:
		maskedVis = []
		for simVis,mask in zip(simDict['vis'][pol], dataDict['msk'][pol]):
			maskedVis.append( simVis.compress(numpy.logical_not(mask)) )
		simVis = numpy.concatenate(maskedVis)
	else:
		maskedVis = []
		for simVis in simDict['vis'][pol]:
			maskedVis.append( numpy.array([simVis[chan]]) )
		simVis = numpy.concatenate(maskedVis)

	# Compute the difference of the two sets of visibilities and return the 
	# absolute value since scipy.optimize.leastsq is looking for real values.
	err = numpy.abs(obsVis) - numpy.abs(simVis)
	
	return numpy.abs(err)


def selfCal(dataDict, simDict, MapSize=30, MapRes=0.5, pol='xx', chan=22, doGain=False, returnDelays=False):
	"""Function used to perform a simple phase self-calibration of data stored in a 
	readUVData dictionary and a model sky stored in a lsl.sim.vis.buildSimSky 
	dictionary for a given polarization and channel."""

	from scipy.optimize import leastsq, fmin, fmin_cg

	# Initial guesses are no phase delays and blaket gains of 0.184
	initialDelays = numpy.zeros(20)
	initialAmps = numpy.ones(20)*0.388
	bestFit = fmin_cg(__residualsSCP, initialDelays, args=(initialAmps, dataDict, simDict, chan), full_output=True)#, xtol=1e-15, ftol=1e-15, maxiter=1000000, maxfun=1000000)#, maxfev=5000, factor=100000)

	# Break the results array into its various components
	bestDelays = bestFit[0][0:20]
	bad = numpy.where( bestDelays < 0 )
	while len(bad[0]) > 0:
		bestDelays[bad[0]] += 1.0
		bad = numpy.where( bestDelays < 0 )
	bad = numpy.where( bestDelays > 1 )
	while len(bad[0]) > 0:
		bestDelays[bad[0]] -= 1.0
		bad = numpy.where( bestDelays > 1 )

	# If we want to run a gain calibration as well, run the minimization using 
	# residualsSCA.  Otherwise, just use the gain guesses from above to provide
	# the "best gains".
	if doGain:
		bestFit = leastsq(__residualsSCA, initialAmps, args=(bestDelays, dataDict, simDict, chan), full_output=True, xtol=1e-7, ftol=1e-7, maxfev=5000, factor=1)
		bestAmps =  bestFit[0][0:20]

		bestFit = leastsq(__residualsSCP, bestDelays, args=(bestAmps, dataDict, simDict, chan), full_output=True, xtol=1e-7, ftol=1e-7, maxfev=5000, factor=100)

		# Break the results array into its various components
		bestDelays = bestFit[0][0:20]
		bad = numpy.where( bestDelays < 0 )
		while len(bad[0]) > 0:
			bestDelays[bad[0]] += 1.0
			bad = numpy.where( bestDelays < 0 )
		bad = numpy.where( bestDelays > 1 )
		while len(bad[0]) > 0:
			bestDelays[bad[0]] -= 1.0
			bad = numpy.where( bestDelays > 1 )
	else:
		bestAmps = initialAmps

	# Report on the fits
	print 'Best Delays: ', bestDelays
	print 'Best Gains:  ', bestAmps
	print 'Message: ', bestFit[3], bestFit[4]

	if returnDelays:
		return (scaleData(dataDict, bestAmps, bestDelays), bestDelays)
	else:
		return scaleData(dataDict, bestAmps, bestDelays)


### Newer Implmentation Based on a New Approach ###


def __selfCalResid(gains, dataDict, simDict, chan, pol):
	"""Private function  """
	
	fq = dataDict['freq'][chan] / 1e9
	cGains = numpy.abs(gains[0])*numpy.exp(2j*numpy.pi*fq*gains[1:])

	obsVis = []
	for vis,wgt in zip(dataDict['vis'][pol], dataDict['wgt'][pol]):
		obsVis.append( numpy.array((wgt*vis)[chan]) )
	obsVis = numpy.concatenate(obsVis)

	simVis = []
	for vis in simDict['vis'][pol]:
		simVis.append( numpy.array(vis[chan]) )
	simVis = numpy.concatenate(simVis)

	X = obsVis / simVis

	gainProd = []
	for i,j in dataDict['bls'][pol]:
		gainProd.append(cGains[i]*cGains[j].conj())
	gainProd = numpy.array(gainProd)

	return (numpy.abs(X - gainProd)**2).sum()


def selfCal2(dataDict, simDict, chan, pol, returnDelays=False):
	from scipy.optimize import leastsq, fmin, fmin_cg

	print "Self-cal start"

	# Initial guesses are no phase delays and blaket gains of 0.28
	initialAmps = numpy.ones(1)*0.388
	initialDelays = numpy.zeros(20)
	initialGains = numpy.concatenate([initialAmps, initialDelays])
	bestFit = fmin_cg(selfCalResid, initialGains, args=(dataDict, simDict, chan, pol), full_output=True)

	# Report on the fits
	bestAmps = numpy.abs(bestFit[0][0])*numpy.ones(20)
	bestDelays = bestFit[0][1:]
	bestGains = bestAmps*numpy.exp(-2j*numpy.pi*bestDelays)
	print 'Best Delays: ', bestDelays
	print 'Best Gains:  ', bestAmps
	print 'Message: ', bestFit[3], bestFit[4]

	if returnDelays:
		return (scaleData(dataDict, bestAmps, bestDelays), bestGains)
	else:
		return scaleData(dataDict, bestAmps, bestDelays)
