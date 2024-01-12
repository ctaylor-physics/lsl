"""
Module for writing correlator output to a UVFITS file.  The classes and 
functions defined in this module are based heavily off the lwda_fits library.

.. note::
    For arrays with between 256 and 2048 antennas, the baseline packing
    follows the MIRIAD convention.
"""

import os
import gc
import math
import numpy as np
from datetime import datetime

from astropy import units as astrounits
from astropy.time import Time as AstroTime
from astropy.utils import iers
from astropy.io import fits as astrofits
from astropy.coordinates import EarthLocation, AltAz, HADec, FK5

from lsl import astro
from lsl.writer.fitsidi import WriterBase

from lsl.misc import telemetry
telemetry.track_module()


__version__ = '0.3'
__all__ = ['Uv',]


UV_VERSION = (1, 0)


def merge_baseline(ant1, ant2, shift=None):
    """
    Merge two stand ID numbers into a single baseline.
    """
    
    if ant1 > 255 or ant2 > 255:
        baseline = ant1*2048 + ant2 + 65536
    else:
        baseline = ant1*256 + ant2
        
    return baseline


def split_baseline(baseline, shift=None):
    """
    Given a baseline, split it into it consistent stand ID numbers.
    """
    
    if baseline >= 65536:
        ant1 = int((baseline - 65536) // 2048)
        ant2 = int((baseline - 65536) % 2048)
    else:
        ant1 = int(baseline // 256)
        ant2 = int(baseline % 256)
        
    return ant1,ant2


class Uv(WriterBase):
    """
    Class for storing visibility data and writing the data, along with array
    geometry, frequency setup, etc., to a UVFITS file that can be read into
    AIPS via the UVLOD task.
    """
    
    def __init__(self, filename, ref_time=0.0, verbose=False, memmap=None, overwrite=False):
        """
        Initialize a new UVFITS object using a filename and a reference time
        given in seconds since the UNIX 1970 epoch, a python datetime object, or a
        string in the format of 'YYYY-MM-DDTHH:MM:SS'.
        
        .. versionchanged:: 1.1.2
            Added the 'memmap' and 'overwrite' keywords to control if the file
            is memory mapped and whether or not to overwrite an existing file,
            respectively.
        """
        
        # File-specific information
        WriterBase.__init__(self, filename, ref_time=ref_time, verbose=verbose)
        
        # Open the file and get going
        if os.path.exists(filename):
            if overwrite:
                os.unlink(filename)
            else:
                raise IOError(f"File '{filename}' already exists")
        self.FITS = astrofits.open(filename, mode='append', memmap=memmap)
        
    def set_geometry(self, site, antennas, bits=8):
        """
        Given a station and an array of stands, set the relevant common observation
        parameters and add entries to the self.array list.
        
        .. versionchanged:: 0.4.0
            Switched over to passing in Antenna instances generated by the
            :mod:`lsl.common.stations` module instead of a list of stand ID
            numbers.
        """
        
        # Make sure that we have been passed 2047 or fewer stands
        if len(antennas) > 2047:
            raise RuntimeError(f"UVFITS supports up to 2047 antennas only, given {len(antennas)}")
            
        # Update the observatory-specific information
        self.siteName = site.name
        
        stands = []
        for ant in antennas:
            stands.append(ant.stand.id)
        stands = np.array(stands)
        
        arrayX, arrayY, arrayZ = site.geocentric_location
        
        xyz = np.zeros((len(stands),3))
        i = 0
        for ant in antennas:
            ecef = ant.stand.earth_location.itrs
            xyz[i,0] = ecef.x.to('m').value
            xyz[i,1] = ecef.y.to('m').value
            xyz[i,2] = ecef.z.to('m').value
            i += 1
            
        # Create the stand mapper
        mapper = {}
        if stands.max() > 2047:
            enableMapper = True
        else:
            enableMapper = False
            
        ants = []
        for i in range(len(stands)):
            ants.append( self._Antenna(stands[i], xyz[i,0], xyz[i,1], xyz[i,2], bits=bits) )
            if enableMapper:
                mapper[stands[i]] = i+1
            else:
                mapper[stands[i]] = stands[i]
                
        # If the mapper has been enabled, tell the user about it
        if enableMapper and self.verbose:
            print("UVFITS: stand ID mapping enabled")
            for key in mapper.keys():
                value = mapper[key]
                print("UVFITS:  stand #%i -> mapped #%i" % (key, value))
                
        self.nAnt = len(ants)
        self.array.append( {'center': [arrayX, arrayY, arrayZ], 'ants': ants, 'mapper': mapper, 'enableMapper': enableMapper, 'inputAnts': antennas} )
        
    def add_comment(self, comment):
        """
        Add a comment to data.
        
        .. versionadded:: 1.2.4
        """
        
        try:
            self._comments.append( comment )
        except AttributeError:
            self._comments = [comment,]
            
    def add_history(self, history):
        """
        Add a history entry to the data.
        
        .. versionadded:: 1.2.4
        """
        
        try:
            self._history.append( history )
        except AttributeError:
            self._history = [history,]
            
    def write(self):
        """
        Fill in the UVFITS file will all of the tables in the
        correct order.
        """
        
        # Validate
        if self.nStokes == 0:
            raise RuntimeError("No polarization setups defined")
        if len(self.freq) == 0:
            raise RuntimeError("No frequency setups defined")
        if len(self.freq) > 1:
            raise RuntimeError("Too many frequency setups defined")
        if self.nAnt == 0:
            raise RuntimeError("No array geometry defined")
        if len(self.data) == 0:
            raise RuntimeError("No visibility data defined")
            
        # Sort the data set
        self.data.sort()
        
        self._write_aipssu_hdu(dummy=True)
        self._write_primary_hdu()
        self._write_aipsan_hdu()
        self._write_aipsfq_hdu()
        self._write_aipssu_hdu()
        self._write_aipsbp_hdu()
        
        # Clear out the data section
        del(self.data[:])
        gc.collect()
        
    def close(self):
        """
        Close out the file.
        """
        
        self.FITS.flush()
        self.FITS.close()
        
    def _add_common_keywords(self, hdr, name, revision):
        """
        Added keywords common to all table headers.
        """
        
        hdr['EXTNAME'] = (name, 'UVFITS table name')
        hdr['EXTVER'] = (1, 'table instance number') 
        hdr['TABREV'] = (revision, 'table format revision number')
        hdr['NO_IF'] = (len(self.freq), 'number of frequency bands')
        
        date = self.ref_time.split('-')
        name = "ZA%s%s%s" % (date[0][2:], date[1], date[2])
        hdr['OBSCODE'] = (name, 'zenith all-sky image')
        
        hdr['ARRNAM'] = self.siteName
        hdr['RDATE'] = (self.ref_time, 'file data reference date')
        
    def _write_primary_hdu(self):
        """
        Write the primary HDU to file.
        """
        
        self._write_aipsan_hdu(dummy=True)
        hrz = astro.hrz_posn(0, 90)
        (arrPos, ag) = self.read_array_geometry(dummy=True)
        (mapper, inverseMapper) = self.read_array_mapper(dummy=True)
        ids = ag.keys()
        
        el = EarthLocation.from_geodetic(arrPos.lng*astrounits.deg, arrPos.lat*astrounits.deg,
                                         height=arrPos.elv*astrounits.m)
        
        first = True
        mList = []
        uList = []
        vList = []
        wList = []
        timeList = []
        dateList = []
        intTimeList = []
        blineList = []
        nameList = []
        sourceList = []
        for dataSet in self.data:
            # Sort the data by packed baseline
            try:
                if len(dataSet.visibilities) != len(order):
                    raise NameError
            except NameError:
                order = dataSet.argsort(mapper=mapper)
                try:
                    del baselineMapped
                except NameError:
                    pass
                    
            # Deal with defininig the values of the new data set
            if dataSet.pol == self.stokes[0]:
                ## Figure out the new date/time for the observation
                utc = astro.taimjd_to_utcjd(dataSet.obsTime)
                date = AstroTime(utc, format='jd', scale='utc')
                utc0 = AstroTime(f"{date.ymdhms[0]}-{date.ymdhms[1]}-{date.ymdhms[2]} 00:00:00", format='iso', scale='utc')
                utc0 = utc0.jd
                try:
                    utcR
                except NameError:
                    utcR = utc0*1.0
                    
                ## Update the observer so we can figure out where the source is
                if dataSet.source == 'z':
                    ### Zenith pointings
                    tc = AltAz(0.0*astrounits.deg, 90.0*astrounits.deg,
                               location=el, obstime=date)
                    equ = tc.transform_to(FK5(equinox=date))
                    
                    ### format 'source' name based on local sidereal time
                    raHms = astro.deg_to_hms(equ.ra.deg)
                    (tsecs, secs) = math.modf(raHms.seconds)
                    name = "ZA%02d%02d%02d%01d" % (raHms.hours, raHms.minutes, int(secs), int(tsecs * 10.0))
                else:
                    ### Real-live sources (ephem.Body instances)
                    equ = FK5(dataSet.source.a_ra*astrounits.rad, dataSet.source.a_dec*astrounits.rad,
                              equinox=date)
                    
                    name = dataSet.source.name
                    
                ## Update the source ID
                sourceID = self._sourceTable.index(name) + 1
                
                ## Compute the uvw coordinates of all baselines
                ha = equ.transform_to(HADec(location=el, obstime=date))
                RA = equ.ra.deg
                HA = ha.ha.hourangle
                dec = ha.dec.deg
                    
                if first is True:
                    sourceRA, sourceDec = RA, dec
                    first = False
                    
                uvwCoords = dataSet.get_uvw(HA, dec, el)
                
                ## Populate the metadata
                ### Add in the new baselines
                try:
                    blineList.extend( baselineMapped )
                except NameError:
                    baselineMapped = []
                    for o in order:
                        antenna1, antenna2 = dataSet.baselines[o]
                        if mapper is None:
                            stand1, stand2 = antenna1.stand.id, antenna2.stand.id
                        else:
                            stand1, stand2 = mapper[antenna1.stand.id], mapper[antenna2.stand.id]
                        baselineMapped.append( merge_baseline(stand1, stand2) ) 
                    blineList.extend( baselineMapped )
                    
                ### Add in the new u, v, and w coordinates
                uList.extend( uvwCoords[order,0] )
                vList.extend( uvwCoords[order,1] )
                wList.extend( uvwCoords[order,2] )
                
                ### Add in the new date/time
                dateList.extend( [utc0-utcR,]*len(dataSet.baselines) )
                timeList.extend( [utc-utc0,]*len(dataSet.baselines) )
                intTimeList.extend( [dataSet.intTime,]*len(dataSet.baselines) )
                
                ### Add in the new new source ID and name
                sourceList.extend( [sourceID,]*len(dataSet.baselines) )
                nameList.extend( [name,]*len(dataSet.baselines) )
                
                ### Zero out the visibility data
                try:
                    if matrix.shape[0] != len(order):
                        raise NameError
                    matrix *= 0.0
                except NameError:
                    matrix = np.zeros((len(order), 1, 1, self.nChan, self.nStokes, 2), dtype=np.float32)
                    
            # Save the visibility data in the right order
            matrix[:,0,0,:,self.stokes.index(dataSet.pol),0] = dataSet.visibilities[order,:].real
            matrix[:,0,0,:,self.stokes.index(dataSet.pol),1] = dataSet.visibilities[order,:].imag
            
            # Deal with saving the data once all of the polarizations have been added to 'matrix'
            if dataSet.pol == self.stokes[-1]:
                mList.append( matrix*1.0 )
                
        nBaseline = len(blineList)
        
        # Create the UV Data table and update its header
        uv = astrofits.GroupData(np.concatenate(mList), parnames=['UU', 'VV', 'WW', 'DATE', 'DATE', 'BASELINE', 'SOURCE', 'INTTIM'], 
                                 pardata=[np.array(uList, dtype=np.float32), np.array(vList, dtype=np.float32), 
                                          np.array(wList, dtype=np.float32), np.array(dateList), np.array(timeList), 
                                          np.array(blineList), np.array(sourceList), 
                                          np.array(intTimeList)], 
                                 parbscales=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0], 
                                 parbzeros=[0.0, 0.0, 0.0, utcR, 0.0, 0.0, 0.0, 0.0], 
                                 bitpix=-32)
        primary = astrofits.GroupsHDU(uv)
        
        primary.header['EXTEND'] = (True, 'indicates UVFITS file')
        primary.header['GROUPS'] = (True, 'indicates UVFITS file')
        primary.header['OBJECT'] = 'BINARYTB'
        primary.header['TELESCOP'] = self.siteName
        primary.header['INSTRUME'] = self.siteName
        primary.header['OBSERVER'] = (self.observer, 'Observer name(s)')
        primary.header['PROJECT'] = (self.project, 'Project name')
        primary.header['ORIGIN'] = 'LSL'
        primary.header['CORRELAT'] = ('LWASWC', 'Correlator used')
        primary.header['FXCORVER'] = ('1', 'Correlator version')
        primary.header['LWATYPE'] = (self.mode, 'LWA FITS file type')
        primary.header['LWAMAJV'] = (UV_VERSION[0], 'LWA UVFITS file format major version')
        primary.header['LWAMINV'] = (UV_VERSION[1], 'LWA UVFITS file format minor version')
        primary.header['DATE-OBS'] = (self.ref_time, 'UVFITS file data collection date')
        ts = str(astro.get_date_from_sys())
        primary.header['DATE-MAP'] = (ts.split()[0], 'UVFITS file creation date')
        
        primary.header['CTYPE2'] = ('COMPLEX', 'axis 2 is COMPLEX axis')
        primary.header['CDELT2'] = 1.0
        primary.header['CRPIX2'] = 1.0
        primary.header['CRVAL2'] = 1.0
        
        primary.header['CTYPE3'] = ('STOKES', 'axis 3 is STOKES axis (polarization)')
        if self.stokes[0] < 0:
            primary.header['CDELT3'] = -1.0
        else:
            primary.header['CDELT3'] = 1.0
        primary.header['CRPIX3'] = 1.0
        primary.header['CRVAL3'] = float(self.stokes[0])
        
        primary.header['CTYPE4'] = ('FREQ', 'axis 4 is FREQ axis (frequency)')
        primary.header['CDELT4'] = self.freq[0].chWidth
        primary.header['CRPIX4'] = self.refPix
        primary.header['CRVAL4'] = self.refVal
        
        primary.header['CTYPE5'] = ('RA', 'axis 5 is RA axis (position of phase center)')
        primary.header['CDELT5'] = 0.0
        primary.header['CRPIX5'] = 1.0
        primary.header['CRVAL5'] = sourceRA
        
        primary.header['CTYPE6'] = ('DEC', 'axis 6 is DEC axis (position of phase center)')
        primary.header['CDELT6'] = 0.0
        primary.header['CRPIX6'] = 1.0
        primary.header['CRVAL6'] = sourceDec
        
        primary.header['TELESCOP'] = self.siteName
        primary.header['OBSERVER'] = self.observer
        primary.header['SORT'] = ('TB', 'data is sorted in [time,baseline] order')
        
        primary.header['VISSCALE'] = (1.0, 'UV data scale factor')
        
        # Write extra header values
        for name in self.extra_keywords:
            primary.header[name] = self.extra_keywords[name]
            
        # Write the comments and history
        try:
            for comment in self._comments:
                primary.header['COMMENT'] = comment
            del self._comments
        except AttributeError:
            pass
        primary.header['COMMENT'] = " FITS (Flexible Image Transport System) format is defined in 'Astronomy and Astrophysics', volume 376, page 359; bibcode: 2001A&A...376..359H"
        try:
            for hist in self._history:
                primary.header['HISTORY'] = hist
            del self._history
        except AttributeError:
            pass
            
        self.FITS.append(primary)
        self.FITS.flush()
        
    def _write_aipsan_hdu(self, dummy=False):
        """
        Define the 'AIPS AN' table .
        """
        
        i = 0
        names = []
        xyz = np.zeros((self.nAnt,3), dtype=np.float64)
        for ant in self.array[0]['ants']:
            xyz[i,:] = np.array([ant.x, ant.y, ant.z])
            names.append(ant.get_name())
            i = i + 1
            
        # Antenna name
        c1 = astrofits.Column(name='ANNAME', format='A8', 
                        array=np.array([ant.get_name() for ant in self.array[0]['ants']]))
        # Station coordinates in meters
        c2 = astrofits.Column(name='STABXYZ', unit='METERS', format='3D', 
                        array=xyz)
        # Station number
        c3 = astrofits.Column(name='NOSTA', format='1J', 
                        array=np.array([self.array[0]['mapper'][ant.id] for ant in self.array[0]['ants']]))
        # Mount type (0 == alt-azimuth)
        c4 = astrofits.Column(name='MNTSTA', format='1J', 
                        array=np.zeros((self.nAnt,), dtype=np.int32))
        # Axis offset in meters
        c5 = astrofits.Column(name='STAXOF', unit='METERS', format='3E', 
                        array=np.zeros((self.nAnt,3), dtype=np.float32))
        # Diameter
        c6 = astrofits.Column(name='DIAMETER', unit='METERS', format='1E', 
                       array=np.ones(self.nAnt, dtype=np.float32)*2.0)
        # Beam FWHM
        c7 = astrofits.Column(name='BEAMFWHM', unit='DEGR/M', format='1E', 
                       array=np.ones(self.nAnt, dtype=np.float32)*360.0)
        # Feed A polarization label
        c8 = astrofits.Column(name='POLTYA', format='A1', 
                        array=np.array([ant.polA['Type'] for ant in self.array[0]['ants']]))
        # Feed A orientation in degrees
        c9 = astrofits.Column(name='POLAA', format='1E', unit='DEGREES', 
                        array=np.array([ant.polA['Angle'] for ant in self.array[0]['ants']], dtype=np.float32))
        # Feed A polarization parameters
        c10 = astrofits.Column(name='POLCALA', format='2E', 
                        array=np.array([ant.polA['Cal'] for ant in self.array[0]['ants']], dtype=np.float32))
        # Feed B polarization label
        c11 = astrofits.Column(name='POLTYB', format='A1', 
                        array=np.array([ant.polB['Type'] for ant in self.array[0]['ants']]))
        # Feed B orientation in degrees
        c12 = astrofits.Column(name='POLAB', format='1E', unit='DEGREES', 
                        array=np.array([ant.polB['Angle'] for ant in self.array[0]['ants']], dtype=np.float32))
        # Feed B polarization parameters
        c13 = astrofits.Column(name='POLCALB', format='2E', 
                        array=np.array([ant.polB['Cal'] for ant in self.array[0]['ants']], dtype=np.float32))
                        
        # Define the collection of columns
        colDefs = astrofits.ColDefs([c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, c11, c12, c13])
        
        # Create the table and fill in the header
        an = astrofits.BinTableHDU.from_columns(colDefs)
        self._add_common_keywords(an.header, 'AIPS AN', 1)
        
        an.header['EXTVER'] = (1, 'array ID')
        an.header['ARRNAM'] = self.siteName
        an.header['FRAME'] = ('GEOCENTRIC', 'coordinate system')
        an.header['NUMORB'] = (0, 'number of orbital parameters')
        an.header['FREQ'] = (self.refVal, 'reference frequency (Hz)')
        an.header['TIMSYS'] = ('UTC', 'time coordinate system')

        date = self.astro_ref_time
        utc0 = date.to_jd()
        gst0 = astro.get_apparent_sidereal_time(utc0)
        an.header['GSTIA0'] = (gst0 * 15, 'GAST (deg) at RDATE 0 hours')
        
        utc1 = utc0 + 1
        gst1 = astro.get_apparent_sidereal_time(utc1)
        if gst1 < gst0:
            gst1 += 24.0
        ds = gst1 - gst0
        deg = ds * 15.0      
        an.header['DEGPDY'] = (360.0 + deg, 'rotation rate of the earth (deg/day)')
        
        refDate = self.astro_ref_time
        refMJD = refDate.to_jd() - astro.MJD_OFFSET
        eop = iers.IERS_Auto.open()
        refAT = AstroTime(refMJD, format='mjd', scale='utc')
        try:
            # Temporary fix for maia.usno.navy.mil being down
            ut1_utc = eop.ut1_utc(refAT)
            pm_xy = eop.pm_xy(refAT)
        except iers.IERSRangeError:
            eop.close()
            with iers.Conf().set_temp('iers_auto_url', 'ftp://cddis.gsfc.nasa.gov/pub/products/iers/finals2000A.all'):
                eop = iers.IERS_Auto.open()
                ut1_utc = eop.ut1_utc(refAT)
                pm_xy = eop.pm_xy(refAT)
                    
        an.header['UT1UTC'] = (ut1_utc.to('s').value, 'difference UT1 - UTC for reference date')
        an.header['IATUTC'] = (astro.leap_secs(utc0), 'TAI - UTC for reference date')
        an.header['POLARX'] = pm_xy[0].to('arcsec').value
        an.header['POLARY'] = pm_xy[1].to('arcsec').value
        
        an.header['ARRAYX'] = (self.array[0]['center'][0], 'array ECEF X coordinate (m)')
        an.header['ARRAYY'] = (self.array[0]['center'][1], 'array ECEF Y coordinate (m)')
        an.header['ARRAYZ'] = (self.array[0]['center'][2], 'array ECEF Z coordinate (m)')
        
        an.header['NOSTAMAP'] = (int(self.array[0]['enableMapper']), 'Mapping enabled for stand numbers')
        
        if dummy:
            self.an = an
            if self.array[0]['enableMapper']:
                self._write_mapper_hdu(dummy=True)
                
        else:
            an.name = 'AIPS AN'
            self.FITS.append(an)
            self.FITS.flush()
            
            if self.array[0]['enableMapper']:
                self._write_mapper_hdu()
                
    def _write_aipsfq_hdu(self):
        """
        Define the 'AIPS FQ' table .
        """
        
        # Frequency setup number
        c1 = astrofits.Column(name='FRQSEL', format='1J', 
                        array=np.array([self.freq[0].id], dtype=np.int32))
        # Frequency offsets in Hz
        c2 = astrofits.Column(name='IF FREQ', format='1D', unit='HZ', 
                        array=np.array([self.freq[0].bandFreq], dtype=np.float64))
        # Channel width in Hz
        c3 = astrofits.Column(name='CH WIDTH', format='1E', unit='HZ', 
                        array=np.array([self.freq[0].chWidth], dtype=np.float32))
        # Total bandwidths of bands
        c4 = astrofits.Column(name='TOTAL BANDWIDTH', format='1E', unit='HZ', 
                        array=np.array([self.freq[0].totalBW], dtype=np.float32))
        # Sideband flag
        c5 = astrofits.Column(name='SIDEBAND', format='1J', 
                        array=np.array([self.freq[0].sideBand], dtype=np.int32))
        
        # Define the collection of columns
        colDefs = astrofits.ColDefs([c1, c2, c3, c4, c5])
        
        # Create the table and fill in the header
        fq = astrofits.BinTableHDU.from_columns(colDefs)
        self._add_common_keywords(fq.header, 'AIPS FQ', 1)
        
        self.FITS.append(fq)
        self.FITS.flush()
        
    def _write_aipsbp_hdu(self):
        """
        Define the 'AIPS BP' table.
        """
        
        # Central time of period covered by record in days
        c1 = astrofits.Column(name='TIME', unit='DAYS', format='1D', 
                        array=np.zeros((self.nAnt,), dtype=np.float64))
        # Duration of period covered by record in days
        c2 = astrofits.Column(name='INTERVAL', unit='DAYS', format='1E',
                        array=(2*np.ones((self.nAnt,), dtype=np.float32)))
        # Source ID
        c3 = astrofits.Column(name='SOURCE ID', format='1J', 
                        array=np.zeros((self.nAnt,), dtype=np.int32))
        # Sub-array number
        c4 = astrofits.Column(name='SUBARRAY', format='1J', 
                        array=np.ones((self.nAnt,), dtype=np.int32))
        # Frequency setup number
        c5 = astrofits.Column(name='FREQ ID', format='1J',
                        array=(np.zeros((self.nAnt,), dtype=np.int32) + self.freq[0].id))
        # Antenna number
        c6 = astrofits.Column(name='ANTENNA', format='1J', 
                        array=self.FITS['AIPS AN'].data.field('NOSTA'))
        # Bandwidth in Hz
        c7 = astrofits.Column(name='BANDWIDTH', unit='HZ', format='1E',
                        array=(np.zeros((self.nAnt,), dtype=np.float32)+self.freq[0].totalBW))
        # Band frequency in Hz
        c8 = astrofits.Column(name='CHN_SHIFT', format='1D',
                        array=(np.zeros((self.nAnt,), dtype=np.float64)+self.freq[0].bandFreq))
        # Reference antenna number (pol. 1)
        c9 = astrofits.Column(name='REFANT 1', format='1J',
                        array=np.ones((self.nAnt,), dtype=np.int32))
        # Solution weight (pol. 1)
        c10 = astrofits.Column(name='WEIGHT 1', format='%dE' % self.nChan,
                        array=np.ones((self.nAnt,self.nChan), dtype=np.float32))
        # Real part of the bandpass (pol. 1)
        c11 = astrofits.Column(name='REAL 1', format='%dE' % self.nChan,
                        array=np.ones((self.nAnt,self.nChan), dtype=np.float32))
        # Imaginary part of the bandpass (pol. 1)
        c12 = astrofits.Column(name='IMAG 1', format='%dE' % self.nChan,
                        array=np.zeros((self.nAnt,self.nChan), dtype=np.float32))
        # Reference antenna number (pol. 2)
        c13 = astrofits.Column(name='REFANT 2', format='1J',
                        array=np.ones((self.nAnt,), dtype=np.int32))
        # Solution weight (pol. 2)
        c14 = astrofits.Column(name='WEIGHT 2', format='%dE' % self.nChan,
                        array=np.ones((self.nAnt,self.nChan), dtype=np.float32))
        # Real part of the bandpass (pol. 2)
        c15 = astrofits.Column(name='REAL 2', format='%dE' % self.nChan,
                        array=np.ones((self.nAnt,self.nChan), dtype=np.float32))
        # Imaginary part of the bandpass (pol. 2)
        c16 = astrofits.Column(name='IMAG 2', format='%dE' % self.nChan,
                        array=np.zeros((self.nAnt,self.nChan), dtype=np.float32))
                        
        colDefs = astrofits.ColDefs([c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, 
                            c11, c12, c13, c14, c15, c16])
                            
        # Create the Bandpass table and update its header
        bp = astrofits.BinTableHDU.from_columns(colDefs)
        self._add_common_keywords(bp.header, 'AIPS BP', 1)
        
        bp.header['NO_ANT'] = self.nAnt
        bp.header['NO_POL'] = 2
        bp.header['NO_CHAN'] = self.nChan
        bp.header['STRT_CHN'] = self.refPix
        bp.header['NO_SHFTS'] = 1
        bp.header['BP_TYPE'] = ' '
        
        self.FITS.append(bp)
        self.FITS.flush()
        
    def _write_aipssu_hdu(self, dummy=False):
        """
        Define the 'AIPS SU' table.
        """
        
        self._write_aipsan_hdu(dummy=True)
        (arrPos, ag) = self.read_array_geometry(dummy=True)
        ids = ag.keys()
        
        el = EarthLocation.from_geodetic(arrPos.lng*astrounits.deg, arrPos.lat*astrounits.deg,
                                         height=arrPos.elv*astrounits.m)
        
        nameList = []
        raList = []
        decList = []
        raPoList = []
        decPoList = []
        sourceID = 0
        for dataSet in self.data:
            if dataSet.pol == self.stokes[0]:
                utc = astro.taimjd_to_utcjd(dataSet.obsTime)
                date = AstroTime(utc, format='jd', scale='utc')
                
                try:
                    currSourceName = dataSet.source.name
                except AttributeError:
                    currSourceName = dataSet.source
                
                if currSourceName not in nameList:
                    sourceID += 1
                    
                    if dataSet.source == 'z':
                        ## Zenith pointings
                        tc = AltAz(0.0*astrounits.deg, 90.0*astrounits.deg,
                                   location=el, obstime=date)
                        equ = tc.transform_to(FK5(equinox=date))
                         
                        # format 'source' name based on local sidereal time
                        raHms = astro.deg_to_hms(equ.ra.deg)
                        (tsecs, secs) = math.modf(raHms.seconds)
                        
                        name = "ZA%02d%02d%02d%01d" % (raHms.hours, raHms.minutes, int(secs), int(tsecs * 10.0))
                        equPo = equ.transform_to(FK5(equinox='J2000'))
                        
                        equ = astro.equ_posn.from_astropy(equ)
                        equPo = astro.equ_posn.from_astropy(equPo)
                        
                    else:
                        ## Real-live sources (ephem.Body instances)
                        name = dataSet.source.name
                        equ = astro.equ_posn(dataSet.source.ra*180/np.pi, dataSet.source.dec*180/np.pi)
                        equPo = astro.equ_posn(dataSet.source.a_ra*180/np.pi, dataSet.source.a_dec*180/np.pi)
                        
                    # current apparent zenith equatorial coordinates
                    raList.append(equ.ra)
                    decList.append(equ.dec)
                    
                    # J2000 zenith equatorial coordinates
                    raPoList.append(equPo.ra)
                    decPoList.append(equPo.dec)
                    
                    # name
                    nameList.append(name)
                    
        nSource = len(nameList)
        
        # Save these for later since we might need them
        self._sourceTable = nameList
        
        # Source ID number
        c1 = astrofits.Column(name='ID. NO.', format='1J', 
                        array=np.arange(1, nSource+1, dtype=np.int32))
        # Source name
        c2 = astrofits.Column(name='SOURCE', format='A16', 
                        array=np.array(nameList))
        # Source qualifier
        c3 = astrofits.Column(name='QUAL', format='1J', 
                        array=np.zeros((nSource,), dtype=np.int32))
        # Calibrator code
        c4 = astrofits.Column(name='CALCODE', format='A4', 
                        array=np.array(('   ',)).repeat(nSource))
        # Stokes I flux density in Jy
        c5 = astrofits.Column(name='IFLUX', format='1E', unit='JY', 
                        array=np.zeros((nSource,), dtype=np.float32))
        # Stokes I flux density in Jy
        c6 = astrofits.Column(name='QFLUX', format='1E', unit='JY', 
                        array=np.zeros((nSource,), dtype=np.float32))
        # Stokes I flux density in Jy
        c7 = astrofits.Column(name='UFLUX', format='1E', unit='JY', 
                        array=np.zeros((nSource,), dtype=np.float32))
        # Stokes I flux density in Jy
        c8 = astrofits.Column(name='VFLUX', format='1E', unit='JY', 
                        array=np.zeros((nSource,), dtype=np.float32))
        # Frequency offset in Hz
        c9 = astrofits.Column(name='FREQOFF', format='1D', unit='HZ',
                       array=np.zeros((nSource,), dtype=np.float64))
        # Bandwidth
        c10 = astrofits.Column(name='BANDWIDTH', format='1D', unit='HZ',
                        array=np.zeros((nSource,), dtype=np.float64))
        # Right ascension at mean equinox in degrees
        c11 = astrofits.Column(name='RAEPO', format='1D', unit='DEGREES', 
                        array=np.array(raPoList))
        # Declination at mean equinox in degrees
        c12 = astrofits.Column(name='DECEPO', format='1D', unit='DEGREES', 
                        array=np.array(decPoList))
        # Epoch
        c13 = astrofits.Column(name='EPOCH', format='1D', unit='YEARS', 
                        array=np.zeros((nSource,), dtype=np.float64) + 2000.0)
        # Apparent right ascension in degrees
        c14 = astrofits.Column(name='RAAPP', format='1D', unit='DEGREES', 
                        array=np.array(raList))
        # Apparent declination in degrees
        c15 = astrofits.Column(name='DECAPP', format='1D', unit='DEGREES', 
                        array=np.array(decList))
        # LSR frame systemic velocity in m/s
        c16 = astrofits.Column(name='LSRVEL', format='1D', unit='M/SEC', 
                        array=np.zeros((nSource,), dtype=np.float64))
        # Line rest frequency in Hz
        c17 = astrofits.Column(name='RESTFREQ', format='1D', unit='HZ', 
                        array=(np.zeros((nSource,), dtype=np.float64) + self.refVal))
        # Proper motion in RA in degrees/day
        c18 = astrofits.Column(name='PMRA', format='1D', unit='DEG/DAY', 
                        array=np.zeros((nSource,), dtype=np.float64))
        # Proper motion in Dec in degrees/day
        c19 = astrofits.Column(name='PMDEC', format='1D', unit='DEG/DAY', 
                        array=np.zeros((nSource,), dtype=np.float64))
                        
        # Define the collection of columns
        colDefs = astrofits.ColDefs([c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, 
                            c11, c12, c13, c14, c15, c16, c17, c18, c19])
        
        # Create the table and fill in the header
        su = astrofits.BinTableHDU.from_columns(colDefs)
        self._add_common_keywords(su.header, 'AIPS SU', 1)
        su.header['FREQID'] = 1
        su.header['VELDEF'] = ''
        su.header['VECTYP'] = ''
        
        if not dummy:
            self.FITS.append(su)
            self.FITS.flush()
            
    def _write_mapper_hdu(self, dummy=False):
        """
        Write a fits table that contains information about mapping stations 
        numbers to actual antenna numbers.  This information can be backed out of
        the names, but this makes the extraction more programmatic.
        """
        
        c1 = astrofits.Column(name='ANNAME', format='A8', 
                        array=np.array([ant.get_name() for ant in self.array[0]['ants']]))
        c2 = astrofits.Column(name='NOSTA', format='1J', 
                        array=np.array([self.array[0]['mapper'][ant.id] for ant in self.array[0]['ants']]))
        c3 = astrofits.Column(name='NOACT', format='1J', 
                        array=np.array([ant.id for ant in self.array[0]['ants']]))
                        
        colDefs = astrofits.ColDefs([c1, c2, c3])
        
        # Create the ID mapping table and update its header
        nsm = astrofits.BinTableHDU.from_columns(colDefs)
        self._add_common_keywords(nsm.header, 'NOSTA_MAPPER', 1)
        
        if dummy:
            self.am = nsm
        else:
            nsm.name = 'NOSTA_MAPPER'
            self.FITS.append(nsm)
            self.FITS.flush()
            
    def read_array_geometry(self, dummy=False):
        """
        Return a tuple with the array geodetic position and the local 
        positions for all antennas defined in the AIPS AN table.
        """
        
        if dummy:
            try:
                ag = self.an
            except AttributeError:
                raise RuntimeError("Temporary 'AIPS AN' table not found.")
                
        else:
            try:
                ag = self.FITS['AIPS AN']
            except IndexError:
                raise RuntimeError("File does not have an 'AIPS AN' table.")
                
        # Array position
        arrayGeo = astro.rect_posn(ag.header['ARRAYX'], ag.header['ARRAYY'], ag.header['ARRAYZ'])
        arrayGeo = astro.get_geo_from_rect(arrayGeo)
        
        # Antenna positions
        antennaGeo = {}
        antenna = ag.data
        antennaID = antenna.field('NOSTA')
        antennaPos = iter(antenna.field('STABXYZ'))
        for id in antennaID:
            antennaGeo[id] = next(antennaPos)
            
        # Return
        return (arrayGeo, antennaGeo)
        
    def read_array_mapper(self, dummy=False):
        """
        Return a tuple with the array NOSTA mapper and inverse mapper (both
        dictionaries.  If the stand IDs have not been mapped, return None for
        both.
        """
        
        if dummy:
            try:
                nsm = self.am
            except AttributeError:
                return (None, None)
                
        else:
            try:
                nsm = self.FITS['NOSTA_MAPPER']
            except KeyError:
                return (None, None)
                
        # Build the mapper and inverseMapper
        mapper = {}
        inverseMapper = {}
        nosta = nsm.data.field('NOSTA')
        noact = nsm.data.field('NOACT')
        for idMapped, idActual in zip(nosta, noact):
            mapper[idActual] = idMapped
            inverseMapper[idMapped] = idActual
            
        # Return
        return (mapper, inverseMapper)
