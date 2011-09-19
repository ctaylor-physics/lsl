# -*- coding: utf-8 -*-

"""
Module for computing spectral kurtosis.

This module is based on:

 * Nita & Gary (2010, PASP 155, 595)
 * Nita & Gary (2010, MNRAS 406, L60)
"""

import numpy

from scipy.special import erf
from scipy.stats import betaprime

__version__ = '0.1'
__revision__ = '$Rev$'
__all__ = ['mean', 'std', 'var', 'skew', 'getLimits', 'spectralFFT', 'spectralPower', '__version__', '__revision__', '__all__']


def mean(M, N=1):
	"""
	Return the expected mean spectral kurtosis value for M points each composed
	of N measurments.
	"""
	
	return 1.0


def std(M, N=1):
	"""
	Return the expected standard deviation of the spectral kurtosis for M points 
	each composed of N measurments.
	"""
	
	return numpy.sqrt( var(M, N) )


def var(M, N=1):
	"""
	Return the expected variance (second central moment) of the spectral kurtosis 
	for M points each composed of N measurments.
	"""

	return 2.0*N*(N+1)*M**2/ float( (M-1)*(M*N+3)*(M*N+2) )


def skew(M, N=1):
	"""
	Return the expected skewness (thrird central moment) of the spectral kurtosis 
	for M points each composed of N measurments.
	"""
	
	m2 = var(M, N)
	
	return 4.0*m2*M / float( (M-1)*(M*N+5)*(M*N+4) ) * ( (N+4)*M*N - 5*N - 2 )


def _alpha(M, N):
	"""
	Determine the value of alpha needed to reproduce the spectral kurtosis PDF via a
	Pearson Type VI distribution (betaprime in scipy.stats world).
	"""
	
	m2 = var(M, N)
	m3 = skew(M, N)

	return 1.0/m3**3*(32*m2**5 - 4*m3*m2**3 + 8*m3**2*m2**2 + m3**2*m2 - m3**3 + (8*m2**3 - m3*m2 + m3**2)*numpy.sqrt( 16*m2**4 + 4*m3**2*m2 + m3**2 ))


def _beta(M, N):
	"""
	Determine the value of beta needed to reproduce the spectral kurtosis PDF via a
	Pearson Type VI distribution (betaprime in scipy.stats world).
	"""
	
	m2 = var(M, N)
	m3 = skew(M, N)

	return 3 + 2*m2/m3**2*(4*m2**2 + numpy.sqrt( 16*m2**4 + 4*m3**2*m2 + m3**2 ))


def _delta(M, N):
	"""
	Determine the value of delta needed to shift a Pearson Type VI distribution (betaprime 
	in scipy.stats world) to a mean value of 1.0
	"""
	
	a = _alpha(M, N)
	b = _beta(M, N)

	return (b - a - 1) / (b - 1)


def getLimits(sigma, M, N=1):
	"""
	Return the limits on the spectral kurtosis value to exclude the specified confidence
	interval in sigma.  The return value is a two-element tuple of lower limit, upper 
	limit.
	"""

	# Convert the sigma to a fraction for the high and low clip levels
	percentClip = ( 1.0 - erf(sigma/numpy.sqrt(2)) ) / 2.0
	
	# Build the Pearson type VI distribution function - parameters then instance
	a = _alpha(M, N)
	b = _beta(M, N)
	d = _delta(M, N)
	
	rv = betaprime(a, b, loc=d)
	
	# Try to get a realistic lower limit, giving up if we hit an overflow error
	try:
		lower = rv.ppf(percentClip)
	except OverflowError:
		lower = mean(M, N) - sigma*std(M, N)
		
	# Try to get a realistic upper limit, giving up if we hit an overflow error
	try:
		upper = rv.ppf(1.0-percentClip)
	except OverflowError:
		upper = mean(M, N) + sigma*std(M, N)
		
	return lower, upper


def spectralFFT(x):
	"""
	Compute the spectral kurtosis for a set of unaveraged FFT measurements.
	For a distribution consistent with Gaussian noise, this value should 
	be ~1.
	"""
	
	# Convert to power
	xPrime = numpy.abs(x)**2
	
	return spectralPower(xPrime, N=1)


def spectralPower(x, N=1):
	"""
	Compute the spectral kurtosis for a set of power measurments averaged over 
	N FFT windows.  For a distribution consistent with Gaussian noise, this value 
	should be ~1.
	"""
	
	M = len(x)
	
	k = M*(x**2).sum()/(x.sum())**2 - 1.0
	k *= (M*N+1)/(M-1)
	
	return k