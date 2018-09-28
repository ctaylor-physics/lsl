# -*- coding: utf-8 -*

"""
This module stores various functions that are needed for computing UV 
coverage and time delays.  The functions in the module:
  * compute the u, v, and w coordinates of all baselines defined by an array 
    of stands
  * compute the track through the uv-plane of a collection of baselines as 
    the Earth rotates.
    
.. versionchanged:: 0.4.0
    Removed function for dealing with meta-data (position, cable length, etc.) 
    for individual stands since these are wrapped in the new :mod:`lsl.common.stations`
    module.
    
.. versionchanged:: 1.0.0
    Generalized the computeUVW() and computeUVTrack() functions.
"""

import numpy

from lsl.common.stations import lwa1
from lsl.common.constants import deg2rad, c as speedOfLight

__version__ = '0.6'
__revision__ = '$Rev$'
__all__ = ['getBaselines', 'baseline2antenna', 'antenna2baseline', 'computeUVW', 'computeUVTrack', 
           'uvUtilsError', '__version__', '__revision__', '__all__']


class uvUtilsError(Exception):
    """Base exception class for this module"""
    
    def __init__(self, strerror, *args, **kwds):
        self.strerror = strerror
        super(uvUtilsError, self).__init__(*args, **kwds)
        
    def __str__(self):
        return "%s" % self.strerror


def getBaselines(antennas, antennas2=None, include_auto=False, indicies=False):
    """
    Generate a list of two-element tuples that describe which antennae
    compose each of the output uvw triplets from computeUVW/computeUVTrack.
    If the indicies keyword is set to True, the two-element tuples 
    contain the indicies of the stands array used, rather than the actual
    stand numbers.
    """

    if include_auto:
        offset = 0
    else:
        offset = 1

    out = []
    N = len(antennas)
    
    # If we don't have an antennas2 array, use antennas again
    if antennas2 is None:
        antennas2 = antennas
    
    for i in range(0, N-offset):
        for j in range(i+offset, N):
            if indicies:
                out.append( (i, j) )
            else:
                out.append( (antennas[i], antennas2[j]) )

    return out
    

def baseline2antenna(baseline, antennas, antennas2=None, baseline_list=None, include_auto=False, indicies=False):
    """
    Given a baseline number, a list of stands, and options of how the base-
    line listed was generated, convert the baseline number to antenna numbers.
    Alternatively, use a list of baselines instead of generating a new list.  
    This utility is useful for figuring out what antennae comprise a baseline.
    """
    
    # If we don't have an antennas2 array, use antennas again
    if antennas2 is None:
        antennas2 = antennas

    # Build up the list of baselines using the options provided
    if baseline_list is None:
        baseline_list = getBaselines(antennas, antennas2=antennas2, include_auto=include_auto, indicies=indicies)
    
    # Select the correct one and return based on the value of indicies
    i,j = baseline_list[baseline]
    return i,j


def antenna2baseline(ant1, ant2, antennas, antennas2=None, baseline_list=None, include_auto=False, indicies=False):
    """
    Given two antenna numbers, a list of stands, and options to how the base-
    line listed was generated, convert the antenna pair to  a baseline number. 
    This utility is useful for picking out a particular pair from a list of
    baselines.
    """
    
    # If we don't have an antennas2 array, use antennas again
    if antennas2 is None:
        antennas2 = antennas

    # Build up the list of baselines using the options provided
    if baseline_list is None:
        baseline_list = getBaselines(antennas, antennas2=antennas2, include_auto=include_auto, indicies=indicies)
    
    # Loop over the baselines until we find one that matches.  If we don't find 
    # one, return -1
    i = 0
    for baseline in baseline_list:
        if ant1 in baseline and ant2 in baseline:
            return i
        else:
            i = i + 1
    else:
        return -1


def computeUVW(antennas, HA=0.0, dec=34.070, freq=49.0e6, site=lwa1, include_auto=False):
    """
    Compute the uvw converate of a baselines formed by a collection of 
    stands.  The coverage is computed at a given HA (in hours) and 
    declination (in degrees) for a given site.  The frequency provided 
    (in Hz) can either as a scalar or as a numpy array.  If more than one 
    frequency is given, the output is a three dimensional with dimensions 
    of baselines, uvw, and frequencies.
    
    .. versionchanged:: 0.4.0
        Switched over to passing in Antenna instances generated by the
        :mod:`lsl.common.station` module instead of a list of stand ID
        numbers.
        
    .. versionchanged:: 1.0.0
        Added a keyword (site) to specify the station used for the 
        observation.
        
    .. versionchanged:: 1.1.2
        Updated to work with lists in a transparent manner.
    """
    
    # Try this so that freq can be either a scalar, a list, or an array
    try: 
        freq.size
        assert(freq.shape != ())
    except (AttributeError, AssertionError):
        freq = numpy.array(freq, ndmin=1)
        
    baselines = getBaselines(antennas, include_auto=include_auto, indicies=True)
    Nbase = len(baselines)
    Nfreq = freq.size
    uvw = numpy.zeros((Nbase,3,Nfreq))

    # Phase center coordinates
    # Convert numbers to radians and, for HA, hours to degrees
    HA2 = HA * 15.0 * deg2rad
    dec2 = dec * deg2rad
    lat2 = site.lat
    
    # Coordinate transformation matrices
    trans1 = numpy.matrix([[0, -numpy.sin(lat2), numpy.cos(lat2)],
                    [1,  0,               0],
                    [0,  numpy.cos(lat2), numpy.sin(lat2)]])
    trans2 = numpy.matrix([[ numpy.sin(HA2),                  numpy.cos(HA2),                 0],
                    [-numpy.sin(dec2)*numpy.cos(HA2),  numpy.sin(dec2)*numpy.sin(HA2), numpy.cos(dec2)],
                    [ numpy.cos(dec2)*numpy.cos(HA2), -numpy.cos(dec2)*numpy.sin(HA2), numpy.sin(dec2)]])
                    
    for k,(i,j) in enumerate(baselines):
        # Go from a east, north, up coordinate system to a celestial equation, 
        # east, north celestial pole system
        xyzPrime = antennas[i].stand - antennas[j].stand
        xyz = trans1*numpy.matrix([[xyzPrime[0]], [xyzPrime[1]], [xyzPrime[2]]])
        
        # Go from CE, east, NCP to u, v, w
        temp = trans2*xyz
        uvw[k,:,:] = temp[:,0] * freq.ravel() / speedOfLight
        
    uvw.shape = (Nbase,3)+freq.shape
    
    return uvw


def computeUVTrack(antennas, dec=34.070, freq=49.0e6, site=lwa1):
    """
    Whereas computeUVW provides the uvw coverage at a particular time, 
    computeUVTrack provides the complete uv plane track for a long 
    integration.  The output is a three dimensional numpy array with 
    dimensions baselines, uv, and 512 points along the track ellipses.  
    Unlike computeUVW, however, only a single frequency (in Hz) can be 
    specified.
    
    .. versionchanged:: 0.4.0
        Switched over to passing in Antenna instances generated by the
        :mod:`lsl.common.station` module instead of a list of stand ID
        numbers.
        
    .. versionchanged:: 1.0.0
        Added a keyword (site) to specify the station used for the 
        observation.
    """
    
    N = len(antennas)
    Nbase = N*(N-1)/2
    uvTrack = numpy.zeros((Nbase,2,512))
    
    # Phase center coordinates
    # Convert numbers to radians and, for HA, hours to degrees
    dec2 = dec * deg2rad
    lat2 = site.lat
    
    # Coordinate transformation matrices
    trans1 = numpy.matrix([[0, -numpy.sin(lat2), numpy.cos(lat2)],
                    [1,  0,               0],
                    [0,  numpy.cos(lat2), numpy.sin(lat2)]])
                    
    count = 0
    for i,j in getBaselines(antennas, indicies=True):
        # Go from a east, north, up coordinate system to a celestial equation, 
        # east, north celestial pole system
        xyzPrime = antennas[i].stand - antennas[j].stand
        xyz = trans1*numpy.matrix([[xyzPrime[0]],[xyzPrime[1]],[xyzPrime[2]]])
        xyz = numpy.ravel(xyz)
        
        uRange = numpy.linspace(-numpy.sqrt(xyz[0]**2 + xyz[1]**2), numpy.sqrt(xyz[0]**2 + xyz[1]**2), num=256)
        vRange1 = numpy.sqrt(xyz[0]**2 + xyz[1]**2 - uRange**2)*numpy.sin(dec2) + xyz[2]*numpy.cos(dec2)
        vRange2 = -numpy.sqrt(xyz[0]**2 + xyz[1]**2 - uRange**2)*numpy.sin(dec2) + xyz[2]*numpy.cos(dec2)
        
        uvTrack[count,0,0:256] = uRange * freq / numpy.array(speedOfLight)
        uvTrack[count,1,0:256] = vRange1 * freq / numpy.array(speedOfLight)
        uvTrack[count,0,256:512] = uRange[::-1] * freq / numpy.array(speedOfLight)
        uvTrack[count,1,256:512] = vRange2[::-1] * freq / numpy.array(speedOfLight)
        count = count + 1
        
    return uvTrack
