"""
Unit test for the lsl.common.sdf module.
"""

import os
import re
import copy
import pytz
import ephem
import tempfile
import unittest
import shutil
from datetime import datetime, timedelta
try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

from astropy.coordinates import Angle as AstroAngle

from lsl.common import sdf, sdfADP as other_sdf
from lsl.common.stations import lwa1, lwasv
import lsl.testing


__version__  = "0.4"
__author__    = "Jayce Dowell"


tbwFile = os.path.join(os.path.dirname(__file__), 'data', 'tbw-sdf.txt')
tbnFile = os.path.join(os.path.dirname(__file__), 'data', 'tbn-sdf.txt')
drxFile = os.path.join(os.path.dirname(__file__), 'data', 'drx-sdf.txt')
solFile = os.path.join(os.path.dirname(__file__), 'data', 'sol-sdf.txt')
jovFile = os.path.join(os.path.dirname(__file__), 'data', 'jov-sdf.txt')
lunFile = os.path.join(os.path.dirname(__file__), 'data', 'lun-sdf.txt')
stpFile = os.path.join(os.path.dirname(__file__), 'data', 'stp-sdf.txt')
spcFile = os.path.join(os.path.dirname(__file__), 'data', 'spc-sdf.txt')
tbfFile = os.path.join(os.path.dirname(__file__), 'data', 'tbf-sdf.txt')
idfFile = os.path.join(os.path.dirname(__file__), 'data', 'drx-idf.txt')


class sdf_tests(unittest.TestCase):
    """A unittest.TestCase collection of unit tests for the lsl.common.sdf
    module."""
    
    def setUp(self):
        """Create the temporary file directory."""

        self.testPath = tempfile.mkdtemp(prefix='test-sdf-', suffix='.tmp')
        
    ### General ###
    
    def test_time(self):
        """Test the sdf.parse_time() function."""
        
        _UTC = pytz.utc
        _EST = pytz.timezone('US/Eastern')
        
        # Different realizations of the same thing
        s1 = "EST 2011-01-01 12:13:14.567"
        s2 = "EST 2011 01 01 12:13:14.567"
        s3 = "EST 2011 Jan 01 12:13:14.567"
        s4 = _EST.localize(datetime(2011, 1, 1, 12, 13, 14, 567000))
        s5 = _EST.localize(datetime(2011, 1, 1, 12, 13, 14, 567123))
        
        self.assertEqual(sdf.parse_time(s1), sdf.parse_time(s2))
        self.assertEqual(sdf.parse_time(s1), sdf.parse_time(s3))
        self.assertEqual(sdf.parse_time(s1), sdf.parse_time(s4))
        self.assertEqual(sdf.parse_time(s1), sdf.parse_time(s5))
        self.assertEqual(sdf.parse_time(s2), sdf.parse_time(s3))
        self.assertEqual(sdf.parse_time(s2), sdf.parse_time(s4))
        self.assertEqual(sdf.parse_time(s2), sdf.parse_time(s5))
        self.assertEqual(sdf.parse_time(s3), sdf.parse_time(s4))
        self.assertEqual(sdf.parse_time(s3), sdf.parse_time(s5))
        self.assertEqual(sdf.parse_time(s4), sdf.parse_time(s5))
        
        # Month name and month number agreement
        for n,m in enumerate(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']):
            s1 = "UTC 2011-%s-14 12:13:14.000" % m
            s2 = "UTC 2011-%02i-14 12:13:14.000" % (n+1)
            s3 = _UTC.localize(datetime(2011, n+1, 14, 12, 13, 14, 0))
            self.assertEqual(sdf.parse_time(s1), sdf.parse_time(s2))
            self.assertEqual(sdf.parse_time(s1), sdf.parse_time(s3))
            
        # Time zone agreement - UTC
        s1 = "2011-01-01 12:13:14.567"
        s2 = "2011 01 01 12:13:14.567"
        s3 = _UTC.localize(datetime(2011, 1, 1, 12, 13, 14, 567000))
        self.assertEqual(sdf.parse_time(s1), sdf.parse_time(s2))
        self.assertEqual(sdf.parse_time(s1), sdf.parse_time(s3))
        self.assertEqual(sdf.parse_time(s2), sdf.parse_time(s3))
        
        # Time zone agreement - local
        for o,z in enumerate(['EST', 'CST', 'MST', 'PST']):
            h = 12
            o = -5 - o
            s1 = "%s 2011 01 01 %02i:13:14.567" % ('UTC', h)
            s2 = "%s 2011 01 01 %02i:13:14.567" % (z, h+o)
            self.assertEqual(sdf.parse_time(s1), sdf.parse_time(s2))
            
        # Something strange
        s1 = "CET 2013-01-08 19:42:00.000"
        s2 = "2013-01-08 18:42:00.000+00:00"
        s3 = "2013-01-08 11:42:00-0700"
        self.assertEqual(sdf.parse_time(s1), sdf.parse_time(s2))
        self.assertEqual(sdf.parse_time(s1), sdf.parse_time(s3))
        self.assertEqual(sdf.parse_time(s2), sdf.parse_time(s3))
        
        # Details
        s1 = "2011 01 02 03:04:05.678"
        out = sdf.parse_time(s1)
        ## Date
        self.assertEqual(out.year, 2011)
        self.assertEqual(out.month, 1)
        self.assertEqual(out.day, 2)
        ## Time
        self.assertEqual(out.hour, 3)
        self.assertEqual(out.minute, 4)
        self.assertEqual(out.second, 5)
        self.assertEqual(out.microsecond, 678000)
        
        # LST at LWA1
        s1 = "LST 2013-01-08 19:42:00.000"
        s2 = "UTC 2013-01-08 19:38:26.723"
        self.assertEqual(sdf.parse_time(s1, station=lwa1), sdf.parse_time(s2))
        
    def test_type_control(self):
        """Test SDF member type control."""
        
        obs = sdf.Observer('Test Observer', 99)
        targ = sdf.DRX('Target', 'Target', '2019/1/1 00:00:00', '00:00:10', 0.0, 90.0, 40e6, 50e6, 7, max_snr=False)
        sess = sdf.Session('Test Session', 1, observations=[targ,])
        sess.drx_beam = 1
        proj = sdf.Project(obs, 'Test Project', 'COMTST', sessions=[sess,])
        
        targ2 = copy.deepcopy(targ)
        targ2.start = '2019/1/1 00:00:10'
        proj.sessions[0].observations.append(targ2)
        self.assertEqual(len(proj.sessions[0].observations), 2)
        
        targ3 = copy.deepcopy(targ)
        targ3.start = '2019/1/1 00:00:20'
        proj.sessions[0].observations.insert(1, targ3)
        self.assertEqual(len(proj.sessions[0].observations), 3)
        
        targ4 = copy.deepcopy(targ)
        targ4.start = '2019/1/1 00:00:30'
        proj.sessions[0].observations[2] = targ4
        self.assertEqual(len(proj.sessions[0].observations), 3)
        
        self.assertRaises(TypeError, proj.sessions.append, 5)
        self.assertRaises(TypeError, proj.sessions[0].observations.append, 6)
        
        with self.assertRaises(TypeError):
            proj.sessions[0].observations[0] = None
        self.assertRaises(TypeError, proj.sessions[0].observations.insert, (-1, 7))
        
    def test_string(self):
        """Test string representations of SDF objects."""
        
        obs = sdf.Observer('Test Observer', 99)
        targ = sdf.DRX('Target', 'Target', '2019/1/1 00:00:00', '00:00:10', 0.0, 90.0, 40e6, 50e6, 7, max_snr=False)
        sess = sdf.Session('Test Session', 1, observations=[targ,])
        sess.drx_beam = 1
        proj = sdf.Project(obs, 'Test Project', 'COMTST', sessions=[sess,])
        
        str(proj)
        repr(proj)
        str(proj.sessions[0])
        repr(proj.sessions[0])
        str(proj.sessions[0].observations[0])
        repr(proj.sessions[0].observations[0])
        
    def test_flat_projects(self):
        """Test single session/observations SDFs."""
        
        obs = sdf.Observer('Test Observer', 99)
        targ = sdf.DRX('Target', 'Target', '2019/1/1 00:00:00', '00:00:10', 0.0, 90.0, 40e6, 50e6, 7, max_snr=False)
        sess = sdf.Session('Test Session', 1, observations=targ)
        sess.drx_beam = 1
        proj = sdf.Project(obs, 'Test Project', 'COMTST', sessions=sess)
        out = proj.render()
        
    def test_ucf_username(self):
        """Test setting the UCF username for auto-copy support."""
        
        obs = sdf.Observer('Test Observer', 99)
        targ = sdf.DRX('Target', 'Target', '2019/1/1 00:00:00', '00:00:10', 0.0, 90.0, 40e6, 50e6, 7, max_snr=False)
        sess = sdf.Session('Test Session', 1, observations=targ)
        sess.drx_beam = 1
        sess.data_return_method = 'UCF'
        sess.ucf_username = 'test'
        proj = sdf.Project(obs, 'Test Project', 'COMTST', sessions=sess)
        out = proj.render()
        self.assertTrue(out.find('ucfuser:test') >= 0)
        
        obs = sdf.Observer('Test Observer', 99)
        targ = sdf.DRX('Target', 'Target', '2019/1/1 00:00:00', '00:00:10', 0.0, 90.0, 40e6, 50e6, 7, max_snr=False)
        sess = sdf.Session('Test Session', 1, observations=targ, comments='This is a comment')
        sess.drx_beam = 1
        sess.data_return_method = 'UCF'
        sess.ucf_username = 'test/dir1'
        proj = sdf.Project(obs, 'Test Project', 'COMTST', sessions=sess)
        out = proj.render()
        self.assertTrue(out.find('ucfuser:test/dir1') >= 0)
        
    ### TBW ###
    
    def test_tbw_parse(self):
        """Test reading in a TBW SDF file."""
        
        project = sdf.parse_sdf(tbwFile)
        
        # Basic file structure
        self.assertEqual(len(project.sessions), 1)
        self.assertEqual(len(project.sessions[0].observations), 2)
        
        # Observational setup - 1
        self.assertEqual(project.sessions[0].observations[0].mode,  'TBW')
        self.assertEqual(project.sessions[0].observations[0].mjd,   55616)
        self.assertEqual(project.sessions[0].observations[0].mpm,       0)
        
        # Observational setup - 2
        self.assertEqual(project.sessions[0].observations[1].mode,  'TBW')
        self.assertEqual(project.sessions[0].observations[1].mjd,   55616)
        self.assertEqual(project.sessions[0].observations[1].mpm,  700000)
        
    def test_tbw_update(self):
        """Test updating TRK_SOL values."""
        
        project = sdf.parse_sdf(tbwFile)
        project.sessions[0].observations[1].start = "MST 2011 Feb 23 17:10:15"
        
        self.assertEqual(project.sessions[0].observations[1].mjd,  55616)
        self.assertEqual(project.sessions[0].observations[1].mpm,  615000)
        
    def test_tbw_write(self):
        """Test writing a TBW SDF file."""
        
        project = sdf.parse_sdf(tbwFile)
        with lsl.testing.SilentVerbose():
            out = project.render(verbose=True)
            
    def test_tbw_errors(self):
        """Test various TBW SDF errors."""
        
        project = sdf.parse_sdf(tbwFile)
        
        # Bad number of TBW bits
        project.sessions[0].observations[0].bits = 6
        self.assertFalse(project.validate())
        
        # Bad number of TBW samples
        project.sessions[0].observations[0].bits = 4
        project.sessions[0].observations[0].samples = 72000000
        self.assertFalse(project.validate())
        
        project.sessions[0].observations[0].bits = 12
        project.sessions[0].observations[0].samples = 72000000
        self.assertFalse(project.validate())
        
    ### TBN ###
    
    def test_tbn_parse(self):
        """Test reading in a TBN SDF file."""
        
        project = sdf.parse_sdf(tbnFile)
        
        # Basic file structure
        self.assertEqual(len(project.sessions), 1)
        self.assertEqual(len(project.sessions[0].observations), 2)
        
        # Observational setup - 1
        self.assertEqual(project.sessions[0].observations[0].mode, 'TBN')
        self.assertEqual(project.sessions[0].observations[0].mjd,  55616)
        self.assertEqual(project.sessions[0].observations[0].mpm,      0)
        self.assertEqual(project.sessions[0].observations[0].dur,  10000)
        self.assertEqual(project.sessions[0].observations[0].freq1, 438261968)
        self.assertEqual(project.sessions[0].observations[0].filter,   7)
        
        # Observational setup - 2
        self.assertEqual(project.sessions[0].observations[1].mode, 'TBN')
        self.assertEqual(project.sessions[0].observations[1].mjd,  55616)
        self.assertEqual(project.sessions[0].observations[1].mpm,  10000)
        self.assertEqual(project.sessions[0].observations[1].dur,  10000)
        self.assertEqual(project.sessions[0].observations[1].freq1, 832697741)
        self.assertEqual(project.sessions[0].observations[1].filter,   7)
        
        # Ordering
        self.assertFalse(project.sessions[0] > project.sessions[0])
        self.assertTrue(project.sessions[0] >= project.sessions[0])
        self.assertFalse(project.sessions[0] < project.sessions[0])
        self.assertTrue(project.sessions[0] <= project.sessions[0])
        self.assertFalse(project.sessions[0] != project.sessions[0])
        self.assertTrue(project.sessions[0] == project.sessions[0])
        
        self.assertTrue(project.sessions[0].observations[0] < project.sessions[0].observations[1])
        self.assertTrue(project.sessions[0].observations[0] <= project.sessions[0].observations[1])
        self.assertFalse(project.sessions[0].observations[0] > project.sessions[0].observations[1])
        self.assertFalse(project.sessions[0].observations[0] >= project.sessions[0].observations[1])
        self.assertTrue(project.sessions[0].observations[0] != project.sessions[0].observations[1])
        self.assertFalse(project.sessions[0].observations[0] == project.sessions[0].observations[1])
        
    def test_tbn_update(self):
        """Test updating TBN values."""
        
        project = sdf.parse_sdf(tbnFile)
        project.sessions[0].observations[1].start = "MST 2011 Feb 23 17:00:15"
        project.sessions[0].observations[1].duration = timedelta(seconds=15)
        project.sessions[0].observations[1].frequency1 = 75e6
        
        self.assertEqual(project.sessions[0].observations[1].mjd,  55616)
        self.assertEqual(project.sessions[0].observations[1].mpm,  15000)
        self.assertEqual(project.sessions[0].observations[1].dur,  15000)
        self.assertEqual(project.sessions[0].observations[1].freq1, 1643482384)
        
        project.sessions[0].observations[1].duration = 16.0
        self.assertEqual(project.sessions[0].observations[1].dur,  16000)
        
        project.sessions[0].observations[1].duration = '16.1'
        self.assertEqual(project.sessions[0].observations[1].dur,  16100)
        
        project.sessions[0].observations[1].duration = '0:01:01.501'
        self.assertEqual(project.sessions[0].observations[1].dur,  61501)
        
        for obs in project.sessions[0].observations:
            obs.mjd += 1
            obs.mpm += 1000
        self.assertEqual(project.sessions[0].observations[1].mjd,  55617)
        self.assertEqual(project.sessions[0].observations[1].mpm,  16000)
        self.assertEqual(project.sessions[0].observations[1].start, 'UTC 2011/02/25 00:00:16.000000')
        
    def test_tbn_write(self):
        """Test writing a TBN SDF file."""
        
        project = sdf.parse_sdf(tbnFile)
        with lsl.testing.SilentVerbose():
            out = project.render(verbose=True)
            
    def test_tbn_errors(self):
        """Test various TBN SDF errors."""
        
        project = sdf.parse_sdf(tbnFile)
        
        with lsl.testing.SilentVerbose():
            # Bad project
            old_id = project.id
            project.id = 'ThisIsReallyLong'
            self.assertFalse(project.validate(verbose=True))
            
            # Bad session
            project.id = old_id
            old_id = project.sessions[0].id
            project.sessions[0].id = 10001
            self.assertFalse(project.validate(verbose=True))
            
            # Bad filter
            project.sessions[0].id = old_id
            project.sessions[0].observations[0].filter = 10
            self.assertFalse(project.validate(verbose=True))
            
            # Bad frequency
            project.sessions[0].observations[0].filter = 7
            project.sessions[0].observations[0].frequency1 = 4.0e6
            project.sessions[0].observations[0].update()
            self.assertFalse(project.validate(verbose=True))
            
            project.sessions[0].observations[0].filter = 7
            project.sessions[0].observations[0].frequency1 = 95.0e6
            project.sessions[0].observations[0].update()
            self.assertFalse(project.validate(verbose=True))
            
            # Bad duration
            project.sessions[0].observations[0].frequency1 = 38.0e6
            project.sessions[0].observations[0].duration = '96:00:00.000'
            project.sessions[0].observations[0].update()
            self.assertFalse(project.validate(verbose=True))
            
            # Bad ASP setup(s)
            project.sessions[0].observations[0].duration = '1:00:00'
            project.sessions[0].observations[0].fee_power = [[1,1] for i in range(250)]
            project.sessions[0].observations[0].update()
            self.assertFalse(project.validate(verbose=True))
            
            project.sessions[0].observations[0].fee_power = [[1,1] for i in range(260)]
            project.sessions[0].observations[0].fee_power[10] = [2,]
            self.assertFalse(project.validate(verbose=True))
            
            project.sessions[0].observations[0].fee_power = [[1,1] for i in range(260)]
            project.sessions[0].observations[0].fee_power[10] = [2,1]
            self.assertFalse(project.validate(verbose=True))
            
            project.sessions[0].observations[0].fee_power = [[1,1] for i in range(260)]
            project.sessions[0].observations[0].fee_power[10] = 2
            self.assertFalse(project.validate(verbose=True))
            
            project.sessions[0].observations[0].fee_power = [[1,1] for i in range(260)]
            for attr in ('asp_atten_1', 'asp_atten_2', 'asp_atten_split', 'asp_filter'):
                setattr(project.sessions[0].observations[0], attr, [1 for i in range(250)])
                project.sessions[0].observations[0].update()
                self.assertFalse(project.validate(verbose=True))
                
                setattr(project.sessions[0].observations[0], attr, [30 for i in range(260)])
                project.sessions[0].observations[0].update()
                self.assertFalse(project.validate(verbose=True))
                
                setattr(project.sessions[0].observations[0], attr, [1 for i in range(260)])
            
    ### DRX - TRK_RADEC ###
    
    def test_drx_parse(self):
        """Test reading in a TRK_RADEC SDF file."""
        
        project = sdf.parse_sdf(drxFile)
        
        # Basic file structure
        self.assertEqual(len(project.sessions), 1)
        self.assertEqual(len(project.sessions[0].observations), 2)
        
        # Observational setup - 1
        self.assertEqual(project.sessions[0].observations[0].mode, 'TRK_RADEC')
        self.assertEqual(project.sessions[0].observations[0].mjd,  55616)
        self.assertEqual(project.sessions[0].observations[0].mpm,      0)
        self.assertEqual(project.sessions[0].observations[0].dur,  10000)
        self.assertEqual(project.sessions[0].observations[0].freq1,  438261968)
        self.assertEqual(project.sessions[0].observations[0].freq2, 1928352663)
        self.assertEqual(project.sessions[0].observations[0].filter,   7)
        self.assertAlmostEqual(project.sessions[0].observations[0].ra, 5.6, 6)
        self.assertAlmostEqual(project.sessions[0].observations[0].dec, 22.0, 6)
        
        # Observational setup - 2
        self.assertEqual(project.sessions[0].observations[1].mode, 'TRK_RADEC')
        self.assertEqual(project.sessions[0].observations[1].mjd,  55616)
        self.assertEqual(project.sessions[0].observations[1].mpm,  10000)
        self.assertEqual(project.sessions[0].observations[1].dur,  10000)
        self.assertEqual(project.sessions[0].observations[1].freq1,  832697741)
        self.assertEqual(project.sessions[0].observations[1].freq2, 1621569285)
        self.assertEqual(project.sessions[0].observations[1].filter,   7)
        self.assertAlmostEqual(project.sessions[0].observations[1].ra, 5.6, 6)
        self.assertAlmostEqual(project.sessions[0].observations[1].dec, 22.0, 6)
        
    def test_drx_update(self):
        """Test updating TRK_RADEC values."""
        
        project = sdf.parse_sdf(drxFile)
        project.sessions[0].observations[1].start = "MST 2011 Feb 23 17:00:15"
        project.sessions[0].observations[1].duration = timedelta(seconds=15)
        project.sessions[0].observations[1].frequency1 = 75e6
        project.sessions[0].observations[1].frequency2 = 76e6
        project.sessions[0].observations[1].ra = AstroAngle('5:30:00', unit='hourangle')
        project.sessions[0].observations[1].dec = ephem.degrees('+22:30:00')
        
        self.assertEqual(project.sessions[0].observations[1].mjd,  55616)
        self.assertEqual(project.sessions[0].observations[1].mpm,  15000)
        self.assertEqual(project.sessions[0].observations[1].dur,  15000)
        self.assertEqual(project.sessions[0].observations[1].freq1, 1643482384)
        self.assertEqual(project.sessions[0].observations[1].freq2, 1665395482)
        self.assertAlmostEqual(project.sessions[0].observations[1].ra, 5.5, 6)
        self.assertAlmostEqual(project.sessions[0].observations[1].dec, 22.5, 6)
        
        project.sessions[0].observations[1].ra = '5h45m00s'
        project.sessions[0].observations[1].dec = '+22d15m00s'
        
        self.assertAlmostEqual(project.sessions[0].observations[1].ra, 5.75, 6)
        self.assertAlmostEqual(project.sessions[0].observations[1].dec, 22.25, 6)
        
        dt0, dt1 = sdf.get_observation_start_stop(project.sessions[0].observations[1])
        self.assertEqual(dt0.year, 2011)
        self.assertEqual(dt0.month, 2)
        self.assertEqual(dt0.day, 24)
        self.assertEqual(dt0.hour, 0)
        self.assertEqual(dt0.minute, 0)
        self.assertEqual(dt0.second, 15)
        self.assertEqual(dt0.microsecond, 0)
        self.assertEqual(dt1.year, 2011)
        self.assertEqual(dt1.month, 2)
        self.assertEqual(dt1.day, 24)
        self.assertEqual(dt1.hour, 0)
        self.assertEqual(dt1.minute, 0)
        self.assertEqual(dt1.second, 30)
        self.assertEqual(dt1.microsecond, 0)
        
    def test_drx_write(self):
        """Test writing a TRK_RADEC SDF file."""
        
        project = sdf.parse_sdf(drxFile)
        with lsl.testing.SilentVerbose():
            out = project.render(verbose=True)
            
        project.sessions[0].observations[0].fee_power = [[1,1] for i in project.sessions[0].observations[0].asp_filter]
        project.sessions[0].observations[0].fee_power[0] = [0,0]
        project.sessions[0].observations[0].fee_power[1] = [0,0]
        out = project.render()
        
        project.sessions[0].observations[0].asp_filter = [1 for i in project.sessions[0].observations[0].asp_filter]
        project.sessions[0].observations[0].asp_filter[0] = 3
        project.sessions[0].observations[0].asp_filter[1] = 3
        out = project.render()
        
        project.sessions[0].observations[0].asp_atten_1 = [1 for i in project.sessions[0].observations[0].asp_filter]
        project.sessions[0].observations[0].asp_atten_1[0] = 3
        project.sessions[0].observations[0].asp_atten_1[1] = 3
        out = project.render()
        
        project.sessions[0].observations[0].asp_atten_2 = [1 for i in project.sessions[0].observations[0].asp_filter]
        project.sessions[0].observations[0].asp_atten_2[0] = 3
        project.sessions[0].observations[0].asp_atten_2[1] = 3
        out = project.render()
        
        project.sessions[0].observations[0].asp_atten_split = [1 for i in project.sessions[0].observations[0].asp_filter]
        project.sessions[0].observations[0].asp_atten_split[0] = 3
        project.sessions[0].observations[0].asp_atten_split[1] = 3
        out = project.render()
        
    def test_drx_errors(self):
        """Test various TRK_RADEC SDF errors."""
        
        project = sdf.parse_sdf(drxFile)
        
        with lsl.testing.SilentVerbose():
            # Bad beam
            project.sessions[0].drx_beam = 6
            self.assertFalse(project.validate(verbose=True))
            
            # No beam (this is allowed now)
            project.sessions[0].drx_beam = -1
            self.assertTrue(project.validate(verbose=True))
            
            # Bad filter
            project.sessions[0].observations[0].filter = 10
            self.assertFalse(project.validate(verbose=True))
            
            # Bad frequency
            project.sessions[0].observations[0].filter = 7
            project.sessions[0].observations[0].frequency1 = 9.0e6
            project.sessions[0].observations[0].update()
            self.assertFalse(project.validate(verbose=True))
            
            project.sessions[0].observations[0].filter = 7
            project.sessions[0].observations[0].frequency1 = 90.0e6
            project.sessions[0].observations[0].update()
            self.assertFalse(project.validate(verbose=True))
            
            project.sessions[0].observations[0].frequency1 = 38.0e6
            project.sessions[0].observations[0].frequency2 = 90.0e6
            project.sessions[0].observations[0].update()
            self.assertFalse(project.validate(verbose=True))
            
            # Bad duration
            project.sessions[0].observations[0].frequency2 = 38.0e6
            project.sessions[0].observations[0].duration = '96:00:00.000'
            project.sessions[0].observations[0].update()
            self.assertFalse(project.validate(verbose=True))
            
            # Bad pointing
            project.sessions[0].observations[0].duration = '00:00:01.000'
            project.sessions[0].observations[0].dec = -72.0
            project.sessions[0].observations[0].update()
            self.assertFalse(project.validate(verbose=True))
            
            # Bad ASP setup(s)
            project.sessions[0].observations[0].dec = 90.0
            project.sessions[0].observations[0].fee_power = [[1,1] for i in range(250)]
            project.sessions[0].observations[0].update()
            self.assertFalse(project.validate(verbose=True))
            
            project.sessions[0].observations[0].fee_power = [[1,1] for i in range(260)]
            project.sessions[0].observations[0].fee_power[10] = [2,]
            self.assertFalse(project.validate(verbose=True))
            
            project.sessions[0].observations[0].fee_power = [[1,1] for i in range(260)]
            project.sessions[0].observations[0].fee_power[10] = [2,1]
            self.assertFalse(project.validate(verbose=True))
            
            project.sessions[0].observations[0].fee_power = [[1,1] for i in range(260)]
            project.sessions[0].observations[0].fee_power[10] = 2
            self.assertFalse(project.validate(verbose=True))
            
            project.sessions[0].observations[0].fee_power = [[1,1] for i in range(260)]
            for attr in ('asp_atten_1', 'asp_atten_2', 'asp_atten_split', 'asp_filter'):
                setattr(project.sessions[0].observations[0], attr, [1 for i in range(250)])
                project.sessions[0].observations[0].update()
                self.assertFalse(project.validate(verbose=True))
                
                setattr(project.sessions[0].observations[0], attr, [30 for i in range(260)])
                project.sessions[0].observations[0].update()
                self.assertFalse(project.validate(verbose=True))
                
                setattr(project.sessions[0].observations[0], attr, [1 for i in range(260)])
                
    ### DRX - TRK_SOL ###
    
    def test_sol_parse(self):
        """Test reading in a TRK_SOL SDF file."""
        
        project = sdf.parse_sdf(solFile)
        
        # Basic file structure
        self.assertEqual(len(project.sessions), 1)
        self.assertEqual(len(project.sessions[0].observations), 2)
        
        # Observational setup - 1
        self.assertEqual(project.sessions[0].observations[0].mode, 'TRK_SOL')
        self.assertEqual(project.sessions[0].observations[0].mjd,  55616)
        self.assertEqual(project.sessions[0].observations[0].mpm,      0)
        self.assertEqual(project.sessions[0].observations[0].dur,  10000)
        self.assertEqual(project.sessions[0].observations[0].freq1,  438261968)
        self.assertEqual(project.sessions[0].observations[0].freq2, 1928352663)
        self.assertEqual(project.sessions[0].observations[0].filter,   7)
        
        # Observational setup - 2
        self.assertEqual(project.sessions[0].observations[1].mode, 'TRK_SOL')
        self.assertEqual(project.sessions[0].observations[1].mjd,  55616)
        self.assertEqual(project.sessions[0].observations[1].mpm,  10000)
        self.assertEqual(project.sessions[0].observations[1].dur,  10000)
        self.assertEqual(project.sessions[0].observations[1].freq1,  832697741)
        self.assertEqual(project.sessions[0].observations[1].freq2, 1621569285)
        self.assertEqual(project.sessions[0].observations[1].filter,   7)
        
    def test_sol_update(self):
        """Test updating TRK_SOL values."""
        
        project = sdf.parse_sdf(solFile)
        project.sessions[0].observations[1].start = "MST 2011 Feb 23 17:00:15"
        project.sessions[0].observations[1].duration = timedelta(seconds=15)
        project.sessions[0].observations[1].frequency1 = 75e6
        project.sessions[0].observations[1].frequency2 = 76e6
        
        self.assertEqual(project.sessions[0].observations[1].mjd,  55616)
        self.assertEqual(project.sessions[0].observations[1].mpm,  15000)
        self.assertEqual(project.sessions[0].observations[1].dur,  15000)
        self.assertEqual(project.sessions[0].observations[1].freq1, 1643482384)
        self.assertEqual(project.sessions[0].observations[1].freq2, 1665395482)
        
    def test_sol_write(self):
        """Test writing a TRK_SOL SDF file."""
        
        project = sdf.parse_sdf(solFile)
        out = project.render()
        
    def test_sol_errors(self):
        """Test various TRK_SOL SDF errors."""
        
        project = sdf.parse_sdf(solFile)
        
        # Bad beam
        project.sessions[0].drx_beam = 6
        self.assertFalse(project.validate())
        
        # No beam (this is allowed now)
        project.sessions[0].drx_beam = -1
        self.assertTrue(project.validate())
        
        # Bad filter
        project.sessions[0].observations[0].filter = 10
        self.assertFalse(project.validate())
        
        # Bad frequency
        project.sessions[0].observations[0].filter = 7
        project.sessions[0].observations[0].frequency1 = 90.0e6
        project.sessions[0].observations[0].update()
        self.assertFalse(project.validate())
        
        project.sessions[0].observations[0].frequency1 = 38.0e6
        project.sessions[0].observations[0].frequency2 = 90.0e6
        project.sessions[0].observations[0].update()
        self.assertFalse(project.validate())
        
        # Bad duration
        project.sessions[0].observations[0].frequency2 = 38.0e6
        project.sessions[0].observations[0].duration = '96:00:00.000'
        project.sessions[0].observations[0].update()
        self.assertFalse(project.validate())
        
    ### DRX - TRK_JOV ###
    
    def test_jov_parse(self):
        """Test reading in a TRK_JOV SDF file."""
        
        project = sdf.parse_sdf(jovFile)
        
        # Basic file structure
        self.assertEqual(len(project.sessions), 1)
        self.assertEqual(len(project.sessions[0].observations), 2)
        
        # Observational setup - 1
        self.assertEqual(project.sessions[0].observations[0].mode, 'TRK_JOV')
        self.assertEqual(project.sessions[0].observations[0].mjd,  55616)
        self.assertEqual(project.sessions[0].observations[0].mpm,      0)
        self.assertEqual(project.sessions[0].observations[0].dur,  10000)
        self.assertEqual(project.sessions[0].observations[0].freq1,  438261968)
        self.assertEqual(project.sessions[0].observations[0].freq2, 1928352663)
        self.assertEqual(project.sessions[0].observations[0].filter,   7)
        
        # Observational setup - 2
        self.assertEqual(project.sessions[0].observations[1].mode, 'TRK_JOV')
        self.assertEqual(project.sessions[0].observations[1].mjd,  55616)
        self.assertEqual(project.sessions[0].observations[1].mpm,  10000)
        self.assertEqual(project.sessions[0].observations[1].dur,  10000)
        self.assertEqual(project.sessions[0].observations[1].freq1,  832697741)
        self.assertEqual(project.sessions[0].observations[1].freq2, 1621569285)
        self.assertEqual(project.sessions[0].observations[1].filter,   7)
        
    def test_jov_update(self):
        """Test updating TRK_JOV values."""
        
        project = sdf.parse_sdf(jovFile)
        project.sessions[0].observations[1].start = "MST 2011 Feb 23 17:00:15"
        project.sessions[0].observations[1].duration = timedelta(seconds=15)
        project.sessions[0].observations[1].frequency1 = 75e6
        project.sessions[0].observations[1].frequency2 = 76e6
        
        self.assertEqual(project.sessions[0].observations[1].mjd,  55616)
        self.assertEqual(project.sessions[0].observations[1].mpm,  15000)
        self.assertEqual(project.sessions[0].observations[1].dur,  15000)
        self.assertEqual(project.sessions[0].observations[1].freq1, 1643482384)
        self.assertEqual(project.sessions[0].observations[1].freq2, 1665395482)
        
    def test_jov_write(self):
        """Test writing a TRK_JOV SDF file."""
        
        project = sdf.parse_sdf(jovFile)
        out = project.render()
        
    def test_jov_errors(self):
        """Test various TRK_JOV SDF errors."""
        
        project = sdf.parse_sdf(jovFile)
        
        # Bad beam
        project.sessions[0].drx_beam = 6
        self.assertFalse(project.validate())
        
        # No beam (this is allowed now)
        project.sessions[0].drx_beam = -1
        self.assertTrue(project.validate())
        
        # Bad filter
        project.sessions[0].observations[0].filter = 10
        self.assertFalse(project.validate())
        
        # Bad frequency
        project.sessions[0].observations[0].filter = 7
        project.sessions[0].observations[0].frequency1 = 90.0e6
        project.sessions[0].observations[0].update()
        self.assertFalse(project.validate())
        
        project.sessions[0].observations[0].frequency1 = 38.0e6
        project.sessions[0].observations[0].frequency2 = 90.0e6
        project.sessions[0].observations[0].update()
        self.assertFalse(project.validate())
        
        # Bad duration
        project.sessions[0].observations[0].frequency2 = 38.0e6
        project.sessions[0].observations[0].duration = '96:00:00.000'
        project.sessions[0].observations[0].update()
        self.assertFalse(project.validate())
        
    ### DRX - TRK_LUN ###
    
    def test_lun_parse(self):
        """Test reading in a TRK_LUN SDF file."""
        
        project = sdf.parse_sdf(lunFile)
        
        # Basic file structure
        self.assertEqual(len(project.sessions), 1)
        self.assertEqual(len(project.sessions[0].observations), 2)
        
        # Observational setup - 1
        self.assertEqual(project.sessions[0].observations[0].mode, 'TRK_LUN')
        self.assertEqual(project.sessions[0].observations[0].mjd,  55615)
        self.assertEqual(project.sessions[0].observations[0].mpm,  43200000)
        self.assertEqual(project.sessions[0].observations[0].dur,  10000)
        self.assertEqual(project.sessions[0].observations[0].freq1,  438261968)
        self.assertEqual(project.sessions[0].observations[0].freq2, 1928352663)
        self.assertEqual(project.sessions[0].observations[0].filter,   7)
        
        # Observational setup - 2
        self.assertEqual(project.sessions[0].observations[1].mode, 'TRK_LUN')
        self.assertEqual(project.sessions[0].observations[1].mjd,  55615)
        self.assertEqual(project.sessions[0].observations[1].mpm,  43210000)
        self.assertEqual(project.sessions[0].observations[1].dur,  10000)
        self.assertEqual(project.sessions[0].observations[1].freq1,  832697741)
        self.assertEqual(project.sessions[0].observations[1].freq2, 1621569285)
        self.assertEqual(project.sessions[0].observations[1].filter,   7)
        
    def test_lun_update(self):
        """Test updating TRK_LUN values."""
        
        project = sdf.parse_sdf(lunFile)
        project.sessions[0].observations[1].start = "MST 2011 Feb 23 5:00:15"
        project.sessions[0].observations[1].duration = timedelta(seconds=15)
        project.sessions[0].observations[1].frequency1 = 75e6
        project.sessions[0].observations[1].frequency2 = 76e6
        
        self.assertEqual(project.sessions[0].observations[1].mjd,  55615)
        self.assertEqual(project.sessions[0].observations[1].mpm,  43215000)
        self.assertEqual(project.sessions[0].observations[1].dur,  15000)
        self.assertEqual(project.sessions[0].observations[1].freq1, 1643482384)
        self.assertEqual(project.sessions[0].observations[1].freq2, 1665395482)
        
    def test_lun_write(self):
        """Test writing a TRK_LUN SDF file."""
        
        project = sdf.parse_sdf(lunFile)
        out = project.render()
        
    def test_lun_errors(self):
        """Test various TRK_LUN SDF errors."""
        
        project = sdf.parse_sdf(lunFile)
        
        # Bad beam
        project.sessions[0].drx_beam = 6
        self.assertFalse(project.validate())
        
        # No beam (this is allowed now)
        project.sessions[0].drx_beam = -1
        self.assertTrue(project.validate())
        
        # Bad filter
        project.sessions[0].observations[0].filter = 10
        self.assertFalse(project.validate())
        
        # Bad frequency
        project.sessions[0].observations[0].filter = 7
        project.sessions[0].observations[0].frequency1 = 90.0e6
        project.sessions[0].observations[0].update()
        self.assertFalse(project.validate())
        
        project.sessions[0].observations[0].frequency1 = 38.0e6
        project.sessions[0].observations[0].frequency2 = 90.0e6
        project.sessions[0].observations[0].update()
        self.assertFalse(project.validate())
        
        # Bad duration
        project.sessions[0].observations[0].frequency2 = 38.0e6
        project.sessions[0].observations[0].duration = '96:00:00.000'
        project.sessions[0].observations[0].update()
        self.assertFalse(project.validate())
        
    ### DRX - STEPPED ###
    
    def test_stp_parse(self):
        """Test reading in a STEPPED SDF file."""
        
        project = sdf.parse_sdf(stpFile)
        
        # Basic file structure
        self.assertEqual(len(project.sessions), 1)
        self.assertEqual(len(project.sessions[0].observations), 2)
        
        # Observational setup - 1
        self.assertEqual(project.sessions[0].observations[0].mode, 'STEPPED')
        self.assertEqual(project.sessions[0].observations[0].mjd,  55616)
        self.assertEqual(project.sessions[0].observations[0].mpm, 440000)
        self.assertEqual(project.sessions[0].observations[0].dur, 300000)
        self.assertEqual(project.sessions[0].observations[0].filter,   7)
        self.assertEqual(project.sessions[0].observations[0].fee_power[0], [1,1])
        self.assertEqual(project.sessions[0].observations[0].asp_filter[0], 2)
        self.assertEqual(project.sessions[0].observations[0].asp_atten_1[0], 10)
        self.assertEqual(project.sessions[0].observations[0].asp_atten_2[0], 12)
        self.assertEqual(project.sessions[0].observations[0].asp_atten_split[0], 14)
        
        # Steps - 1
        self.assertEqual(len(project.sessions[0].observations[0].steps), 4)
        for i in range(4):
            self.assertEqual(project.sessions[0].observations[0].steps[i].is_radec, project.sessions[0].observations[0].is_radec)
            self.assertEqual(project.sessions[0].observations[0].steps[i].freq1,  832697741)
            self.assertEqual(project.sessions[0].observations[0].steps[i].freq2, 1621569285)
        self.assertAlmostEqual(project.sessions[0].observations[0].steps[0].c1, 90.0, 6)
        self.assertAlmostEqual(project.sessions[0].observations[0].steps[0].c2, 45.0, 6)
        self.assertEqual(project.sessions[0].observations[0].steps[0].dur, 60000)
        self.assertAlmostEqual(project.sessions[0].observations[0].steps[-1].c1, 0.0, 6)
        self.assertAlmostEqual(project.sessions[0].observations[0].steps[-1].c2, 1.0, 6)
        self.assertEqual(project.sessions[0].observations[0].steps[-1].dur, 120000)
        
        # Observational setup - 2
        self.assertEqual(project.sessions[0].observations[1].mode, 'STEPPED')
        self.assertEqual(project.sessions[0].observations[1].mjd,  55616)
        self.assertEqual(project.sessions[0].observations[1].mpm, 800000)
        self.assertEqual(project.sessions[0].observations[1].dur, 180000)
        self.assertEqual(project.sessions[0].observations[1].filter,   7)
        self.assertEqual(project.sessions[0].observations[1].fee_power[0], [1,0])
        self.assertEqual(project.sessions[0].observations[1].asp_filter[0], 1)
        self.assertEqual(project.sessions[0].observations[1].asp_atten_1[0], 11)
        self.assertEqual(project.sessions[0].observations[1].asp_atten_2[0], 13)
        self.assertEqual(project.sessions[0].observations[1].asp_atten_split[0], 15)
        
        # Steps - 2
        self.assertEqual(len(project.sessions[0].observations[1].steps), 2)
        for i in range(2):
            self.assertEqual(project.sessions[0].observations[1].steps[i].is_radec, project.sessions[0].observations[1].is_radec)
            self.assertEqual(project.sessions[0].observations[1].steps[i].freq1,  832697741)
            self.assertEqual(project.sessions[0].observations[1].steps[i].freq2, 1621569285)
        self.assertAlmostEqual(project.sessions[0].observations[1].steps[0].c1, 0.0, 6)
        self.assertAlmostEqual(project.sessions[0].observations[1].steps[0].c2, 90.0, 6)
        self.assertEqual(project.sessions[0].observations[1].steps[0].dur, 60000)
        self.assertAlmostEqual(project.sessions[0].observations[1].steps[-1].c1, 12.0, 6)
        self.assertAlmostEqual(project.sessions[0].observations[1].steps[-1].c2, 80.0, 6)
        self.assertEqual(project.sessions[0].observations[1].steps[-1].dur, 120000)
        
    def test_stp_update(self):
        """Test updating a STEPPED SDF file."""
        
        project = sdf.parse_sdf(stpFile)
        project.sessions[0].observations[1].start = "MST 2011 Feb 23 17:00:15"
        for step in project.sessions[0].observations[1].steps:
            step.duration = timedelta(seconds=15)
            step.frequency1 = 75e6
            step.frequency2 = 76e6
            step.c1 = ephem.hours('10:30:00')
            step.c2 = ephem.degrees('89:30:00')
        project.sessions[0].observations[1].update()
        
        self.assertEqual(project.sessions[0].observations[1].mjd,  55616)
        self.assertEqual(project.sessions[0].observations[1].mpm,  15000)
        self.assertEqual(project.sessions[0].observations[1].dur,  30000)
        for step in project.sessions[0].observations[1].steps:
            self.assertEqual(step.dur, 15000)
            self.assertEqual(step.freq1, 1643482384)
            self.assertEqual(step.freq2, 1665395482)
            self.assertEqual(step.c1, 10.5)
            self.assertEqual(step.c2, 89.5)
            
        project = sdf.parse_sdf(stpFile)
        project.sessions[0].observations[1].is_radec = False
        project.sessions[0].observations[1].start = "MST 2011 Feb 23 17:00:15"
        for step in project.sessions[0].observations[1].steps:
            step.is_radec = False
            step.duration = timedelta(seconds=15)
            step.frequency1 = 75e6
            step.frequency2 = 76e6
            step.c1 = ephem.hours('10:30:00')
            step.c2 = ephem.degrees('89:30:00')
        project.sessions[0].observations[1].update()
        
        self.assertEqual(project.sessions[0].observations[1].mjd,  55616)
        self.assertEqual(project.sessions[0].observations[1].mpm,  15000)
        self.assertEqual(project.sessions[0].observations[1].dur,  30000)
        for step in project.sessions[0].observations[1].steps:
            self.assertFalse(step.is_radec)
            self.assertEqual(step.dur, 15000)
            self.assertEqual(step.freq1, 1643482384)
            self.assertEqual(step.freq2, 1665395482)
            self.assertEqual(step.c1, 10.5*15)
            self.assertEqual(step.c2, 89.5)
        
    def test_stp_write(self):
        """Test writing a STEPPED SDF file."""
        
        project = sdf.parse_sdf(stpFile)
        with lsl.testing.SilentVerbose():
            out = project.render(verbose=True)
            
    def test_stp_errors(self):
        """Test various STEPPED SDF errors."""
        
        project = sdf.parse_sdf(stpFile)
        
        # Bad beam
        project.sessions[0].drx_beam = 6
        self.assertFalse(project.validate())
        
        # No beam (this is allowed now)
        project.sessions[0].drx_beam = -1
        self.assertTrue(project.validate())
        
        # Bad filter
        project.sessions[0].observations[0].filter = 10
        self.assertFalse(project.validate())
        
        # Bad frequency
        project.sessions[0].observations[0].filter = 7
        project.sessions[0].observations[0].steps[0].frequency1 = 90.0e6
        project.sessions[0].observations[0].update()
        self.assertFalse(project.validate())
        
        project.sessions[0].observations[0].steps[0].frequency1 = 38.0e6
        project.sessions[0].observations[0].steps[1].frequency2 = 90.0e6
        project.sessions[0].observations[0].update()
        self.assertFalse(project.validate())
        
        # Bad duration
        project.sessions[0].observations[0].steps[1].frequency2 = 38.0e6
        project.sessions[0].observations[0].steps[2].duration = '96:00:00.000'
        project.sessions[0].observations[0].update()
        self.assertFalse(project.validate())
        
        # Bad pointing
        project.sessions[0].observations[0].steps[2].duration = '00:00:01.000'
        with self.assertRaises(ValueError):
            project.sessions[0].observations[0].steps[2].c2 = -72.0
            
        # Bad pointing
        project.sessions[0].observations[0].steps[2].c2 = 90.0
        with self.assertRaises(ValueError):
            project.sessions[0].observations[0].steps[2].c1 = -72.0
            
    ### DRX - STEPPED with delays and gains ###
    
    def test_spc_parse(self):
        """Test reading in a STEPPED Delay and Gain SDF file."""
        
        project = sdf.parse_sdf(spcFile)
        
        # Basic file structure
        self.assertEqual(len(project.sessions), 1)
        self.assertEqual(len(project.sessions[0].observations), 1)
        
        # Observational setup - 1
        self.assertEqual(project.sessions[0].observations[0].mode, 'STEPPED')
        self.assertEqual(project.sessions[0].observations[0].mjd,  55616)
        self.assertEqual(project.sessions[0].observations[0].mpm, 440000)
        self.assertEqual(project.sessions[0].observations[0].dur,  60000)
        self.assertEqual(project.sessions[0].observations[0].filter,   7)
        
        # Steps - 1
        self.assertEqual(len(project.sessions[0].observations[0].steps), 1)
        self.assertEqual(project.sessions[0].observations[0].steps[0].is_radec, project.sessions[0].observations[0].is_radec)
        self.assertAlmostEqual(project.sessions[0].observations[0].steps[0].c1, 90.0, 6)
        self.assertAlmostEqual(project.sessions[0].observations[0].steps[0].c2, 45.0, 6)
        self.assertEqual(project.sessions[0].observations[0].steps[0].freq1,  832697741)
        self.assertEqual(project.sessions[0].observations[0].steps[0].freq2, 1621569285)
        self.assertEqual(project.sessions[0].observations[0].steps[0].dur, 60000)
        
        # Delays - 1
        for i in range(260):
            self.assertEqual(project.sessions[0].observations[0].steps[0].delays[i], 0)
            
        # Gains - 1
        for i in range(260):
            self.assertEqual(project.sessions[0].observations[0].steps[0].gains[i][0][0], 1)
            self.assertEqual(project.sessions[0].observations[0].steps[0].gains[i][0][1], 0)
            self.assertEqual(project.sessions[0].observations[0].steps[0].gains[i][1][0], 0)
            self.assertEqual(project.sessions[0].observations[0].steps[0].gains[i][1][1], 1)
            
    def test_spc_write(self):
        """Test writing a STEPPED Delay and Gain SDF file."""
        
        project = sdf.parse_sdf(spcFile)
        out = project.render()
        
    def test_spectrometer(self):
        """Test parsing DR spectrometer configurations."""
        project = sdf.parse_sdf(drxFile)
        
        # Good spectrometer settings
        for channels in (2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192):
            for ints in (384, 768, 1536, 3072, 6144, 12288, 24576, 49152, 98304, 196608):
                for mode in (None, '', 'XXYY', 'IV', 'IQUV'):
                    ## Method 1
                    project.sessions[0].spcSetup = [channels, ints]
                    if mode in (None, ''):
                        project.sessions[0].spcMetatag = mode
                    else:
                        project.sessions[0].spcMetatag = '{Stokes=%s}' % mode
                    self.assertTrue(project.validate())
                    
                    ## Method 2
                    project.sessions[0].spectrometer_channels = channels
                    project.sessions[0].spectrometer_integration = ints
                    if mode in (None, ''):
                        project.sessions[0].spectrometer_metatag = mode
                    else:
                        project.sessions[0].spectrometer_metatag = 'Stokes=%s' % mode
                    self.assertEqual(project.sessions[0].spcSetup[0], channels)
                    self.assertEqual(project.sessions[0].spcSetup[1], ints)
                    self.assertEqual(project.sessions[0].spcMetatag, None if mode in (None, '') else '{Stokes=%s}' % mode)
                    self.assertTrue(project.validate())
                    
        # Bad channel count
        project.sessions[0].spcSetup = [31, 6144]
        self.assertFalse(project.validate())
        
        # Bad integration count
        project.sessions[0].spcSetup = [32, 6145]
        self.assertFalse(project.validate())
        
        # Unsupported mode
        for mode in ('XX', 'XY', 'YX', 'YY', 'XXXYYXYY', 'I', 'Q', 'U', 'V'):
            project.sessions[0].spcSetup = [32, 6144]
            project.sessions[0].spcMetatag = '{Stokes=%s}' % mode
            self.assertFalse(project.validate())
            
    ### DRX - Beam/Dipole Mode ###
    
    def test_beamdipole_update(self):
        """Test updating beam/dipole mode values."""
        
        project = sdf.parse_sdf(drxFile)
        project.sessions[0].observations[1].set_beamdipole_mode(73)
        
        self.assertTrue(project.sessions[0].observations[0].beamDipole is     None)
        self.assertTrue(project.sessions[0].observations[1].beamDipole is not None)
        
        project.sessions[0].observations[1].set_beamdipole_mode(0)
        self.assertTrue(project.sessions[0].observations[0].beamDipole is None)
        self.assertTrue(project.sessions[0].observations[1].beamDipole is None)
        
    def test_beamdipole_write(self):
        """Test writing a beam/dipole mode SDF file."""
        
        project = sdf.parse_sdf(drxFile)
        project.sessions[0].observations[1].set_beamdipole_mode(73)
        out = project.render()
        
    def test_beamdiploe_errors(self):
        """Test various beam/dipole mode SDF errors."""
        
        project = sdf.parse_sdf(drxFile)
        project.sessions[0].observations[0].set_beamdipole_mode(73)
        
        # Bad dipole
        self.assertRaises(ValueError, project.sessions[0].observations[0].set_beamdipole_mode, -1)
        self.assertRaises(ValueError, project.sessions[0].observations[0].set_beamdipole_mode, 3000)
        
        # Bad beam gain
        self.assertRaises(ValueError, project.sessions[0].observations[0].set_beamdipole_mode, 73, beam_gain=-0.1)
        self.assertRaises(ValueError, project.sessions[0].observations[0].set_beamdipole_mode, 73, beam_gain=1.1)
        
        # Bad dipole gain
        self.assertRaises(ValueError, project.sessions[0].observations[0].set_beamdipole_mode, 73, dipole_gain=-0.1)
        self.assertRaises(ValueError, project.sessions[0].observations[0].set_beamdipole_mode, 73, dipole_gain=1.1)
        
        # Bad polarization
        self.assertRaises(ValueError, project.sessions[0].observations[0].set_beamdipole_mode, 73, pol='L')
        self.assertRaises(ValueError, project.sessions[0].observations[0].set_beamdipole_mode, 73, pol='R')
        
    def test_beamdipole_errors(self):
        """Test various beam/dipole mode SDF errors."""
        
        project = sdf.parse_sdf(drxFile)
        project.sessions[0].observations[0].set_beamdipole_mode(73)
        
        # Bad dipole
        self.assertRaises(ValueError, project.sessions[0].observations[0].set_beamdipole_mode, -1)
        self.assertRaises(ValueError, project.sessions[0].observations[0].set_beamdipole_mode, 3000)
        
        # Bad beam gain
        self.assertRaises(ValueError, project.sessions[0].observations[0].set_beamdipole_mode, 73, beam_gain=-0.1)
        self.assertRaises(ValueError, project.sessions[0].observations[0].set_beamdipole_mode, 73, beam_gain=1.1)
        
        # Bad dipole gain
        self.assertRaises(ValueError, project.sessions[0].observations[0].set_beamdipole_mode, 73, dipole_gain=-0.1)
        self.assertRaises(ValueError, project.sessions[0].observations[0].set_beamdipole_mode, 73, dipole_gain=1.1)
        
        # Bad polarization
        self.assertRaises(ValueError, project.sessions[0].observations[0].set_beamdipole_mode, 73, pol='L')
        self.assertRaises(ValueError, project.sessions[0].observations[0].set_beamdipole_mode, 73, pol='R')
        
    def test_stepped_beamdipole_update(self):
        """Test updating STEPPED beam/dipole mode values."""
        
        project = sdf.parse_sdf(stpFile)
        project.sessions[0].observations[1].set_beamdipole_mode(73)
        
        self.assertTrue(project.sessions[0].observations[0].beamDipole is     None)
        self.assertTrue(project.sessions[0].observations[1].beamDipole is not None)
        
        project.sessions[0].observations[1].set_beamdipole_mode(0)
        self.assertTrue(project.sessions[0].observations[0].beamDipole is None)
        self.assertTrue(project.sessions[0].observations[1].beamDipole is None)
        
    def test_stepped_beamdipole_write(self):
        """Test writing a STEPPED beam/dipole mode SDF file."""
        
        project = sdf.parse_sdf(stpFile)
        project.sessions[0].observations[1].set_beamdipole_mode(73)
        out = project.render()
        
    def test_stepped_beamdipole_errors(self):
        """Test various STEPPED beam/dipole mode SDF errors."""
        
        project = sdf.parse_sdf(stpFile)
        project.sessions[0].observations[0].set_beamdipole_mode(73)
        
        # Bad dipole
        self.assertRaises(ValueError, project.sessions[0].observations[0].set_beamdipole_mode, -1)
        self.assertRaises(ValueError, project.sessions[0].observations[0].set_beamdipole_mode, 3000)
        
        # Bad beam gain
        self.assertRaises(ValueError, project.sessions[0].observations[0].set_beamdipole_mode, 73, beam_gain=-0.1)
        self.assertRaises(ValueError, project.sessions[0].observations[0].set_beamdipole_mode, 73, beam_gain=1.1)
        
        # Bad dipole gain
        self.assertRaises(ValueError, project.sessions[0].observations[0].set_beamdipole_mode, 73, dipole_gain=-0.1)
        self.assertRaises(ValueError, project.sessions[0].observations[0].set_beamdipole_mode, 73, dipole_gain=1.1)
        
        # Bad polarization
        self.assertRaises(ValueError, project.sessions[0].observations[0].set_beamdipole_mode, 73, pol='L')
        self.assertRaises(ValueError, project.sessions[0].observations[0].set_beamdipole_mode, 73, pol='R')
        
    ### TBF ###
    
    def test_tbf_parse(self):
        """Test reading in a TBF SDF file."""
        
        self.assertRaises(RuntimeError, sdf.parse_sdf, tbfFile)
        
    def test_tbf_append(self):
        """Test appending a TBF observation to an LWA1 session."""
        
        project = sdf.parse_sdf(tbnFile)
        
        obs = other_sdf.TBF('TBF', 'TBF', '2020/4/30 01:23:45.5', 40e6, 75e6, 7, 196000)
        self.assertRaises(TypeError, project.sessions[0].append, obs)
        
    ### Misc. ###
    
    def test_auto_update(self):
        """Test project auto-update on render."""
        
        # Part 1 - frequency and duration
        project = sdf.parse_sdf(drxFile)
        project.sessions[0].observations[1].frequency1 = 75e6
        project.sessions[0].observations[1].duration = '00:01:31.000'

        fh = open(os.path.join(self.testPath, 'sdf.txt'), 'w')		
        fh.write(project.render())
        fh.close()
        
        project = sdf.parse_sdf(os.path.join(self.testPath, 'sdf.txt'))
        self.assertEqual(project.sessions[0].observations[1].freq1, 1643482384)
        self.assertEqual(project.sessions[0].observations[1].dur, 91000)
        
        # Part 2 - frequency and duration (timedelta)
        project = sdf.parse_sdf(drxFile)
        project.sessions[0].observations[1].frequency1 = 75e6
        project.sessions[0].observations[1].duration = timedelta(minutes=1, seconds=31, microseconds=1000)

        fh = open(os.path.join(self.testPath, 'sdf.txt'), 'w')		
        fh.write(project.render())
        fh.close()
        
        project = sdf.parse_sdf(os.path.join(self.testPath, 'sdf.txt'))
        self.assertEqual(project.sessions[0].observations[1].freq1, 1643482384)
        self.assertEqual(project.sessions[0].observations[1].dur, 91001)
        
        # Part 3 - frequency and start time
        project = sdf.parse_sdf(drxFile)
        project.sessions[0].observations[1].frequency2 = 75e6
        project.sessions[0].observations[1].start = "MST 2011 Feb 23 17:00:15"

        fh = open(os.path.join(self.testPath, 'sdf.txt'), 'w')		
        fh.write(project.render())
        fh.close()
        
        project = sdf.parse_sdf(os.path.join(self.testPath, 'sdf.txt'))
        self.assertEqual(project.sessions[0].observations[1].freq2, 1643482384)
        self.assertEqual(project.sessions[0].observations[1].mjd,  55616)
        self.assertEqual(project.sessions[0].observations[1].mpm,  15000)
        
        # Part 4 - frequency and start time (timedelta)
        project = sdf.parse_sdf(drxFile)
        _MST = pytz.timezone('US/Mountain')
        project.sessions[0].observations[1].frequency2 = 75e6
        project.sessions[0].observations[1].start = _MST.localize(datetime(2011, 2, 23, 17, 00, 30, 1000))

        fh = open(os.path.join(self.testPath, 'sdf.txt'), 'w')		
        fh.write(project.render())
        fh.close()
        
        project = sdf.parse_sdf(os.path.join(self.testPath, 'sdf.txt'))
        self.assertEqual(project.sessions[0].observations[1].freq2, 1643482384)
        self.assertEqual(project.sessions[0].observations[1].mjd,  55616)
        self.assertEqual(project.sessions[0].observations[1].mpm,  30001)
        
    def test_set_station(self):
        """Test the set stations functionlity."""
        
        project = sdf.parse_sdf(drxFile)
        project.sessions[0].station = lwa1
        self.assertTrue(project.validate())
        
        with self.assertRaises(ValueError):
            project.sessions[0].station = lwasv
            
    def test_is_valid(self):
        """Test whether or not is_valid works."""
        
        self.assertTrue(sdf.is_valid(tbwFile))
        self.assertTrue(sdf.is_valid(tbnFile))
        self.assertTrue(sdf.is_valid(drxFile))
        self.assertTrue(sdf.is_valid(solFile))
        self.assertTrue(sdf.is_valid(jovFile))
        self.assertTrue(sdf.is_valid(stpFile))
        self.assertTrue(sdf.is_valid(spcFile))
        
    def test_is_not_valid(self):
        """Test whether or not is_valid works on LWA-SV and IDF files."""
        
        self.assertFalse(sdf.is_valid(tbfFile))
        self.assertFalse(sdf.is_valid(idfFile))
        
    def test_username(self):
        """Test setting auto-copy parameters."""
        
        project = sdf.parse_sdf(drxFile)
        project.sessions[0].data_return_method = 'UCF'
        project.sessions[0].ucf_username = 'jdowell'
        out = project.render()
        
        self.assertTrue(out.find('Requested data return method is UCF') > 0)
        self.assertTrue(out.find('ucfuser:jdowell') > 0)
        
        project.writeto(os.path.join(self.testPath, 'sdf.txt'))		
        
        project = sdf.parse_sdf(os.path.join(self.testPath, 'sdf.txt'))
        out = project.render()
        
        self.assertTrue(out.find('Requested data return method is UCF') > 0)
        self.assertTrue(out.find('ucfuser:jdowell') > 0)
        
    def tearDown(self):
        """Remove the test path directory and its contents"""

        shutil.rmtree(self.testPath, ignore_errors=True)


class sdf_test_suite(unittest.TestSuite):
    """A unittest.TestSuite class which contains all of the lsl.common.sdf units 
    tests."""
    
    def __init__(self):
        unittest.TestSuite.__init__(self)
        
        loader = unittest.TestLoader()
        self.addTests(loader.loadTestsFromTestCase(sdf_tests)) 


if __name__ == '__main__':
    unittest.main()
