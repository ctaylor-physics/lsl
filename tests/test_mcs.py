"""
Unit test for the lsl.common.mcs module.
"""

import os
import unittest
from datetime import datetime

from lsl.common import mcs


__version__  = "0.1"
__author__    = "Jayce Dowell"


class mcs_tests(unittest.TestCase):
    """A unittest.TestCase collection of unit tests for the lsl.common.mcs
    module."""
    
    def test_delay_conversion(self):
        """Test the MCS delay conversion"""
        
        delay_in = 5.0
        delay_out = mcs.mcsd_to_delay(mcs.delay_to_mcsd(delay_in))
        self.assertTrue(abs(delay_in-delay_out) < 1e9/196e6/16) # Within 1/16 of a sample
        
    def test_gain_conversion(self):
        """Test the MCS gain conversion"""
        
        gain_in = 0.5
        gain_out = mcs.mcsg_to_gain(mcs.gain_to_mcsg(0.5))
        self.assertTrue(abs(gain_in-gain_out) < 1/2.**15)
        
    def test_datetime(self):
        """Test the datetime to MJD, MPM conversion"""
        
        dt = datetime.strptime("2012-06-15 06:34:09", "%Y-%m-%d %H:%M:%S")
        mjd, mpm = mcs.datetime_to_mjdmpm(dt)
        
        self.assertEqual(mjd, 56093)
        self.assertEqual(mpm, 23649000)
    
    def test_mjdmpm(self):
        """Test the MJD, MPM to datetime conversion"""
        
        mjd, mpm = 56093, 23649000
        dt = mcs.mjdmpm_to_datetime(mjd, mpm)
        
        self.assertEqual(dt.strftime("%Y-%m-%d %H:%M:%S"), "2012-06-15 06:34:09")
        
    def test_summary_limits(self):
        """Test valid summary values"""
        
        for i in range(0, 6+1):
            mcs.SummaryCode(i)
        self.assertRaises(ValueError, mcs.SummaryCode, 7)
        
    def test_sid_limits(self):
        """Test valid subsystem ID values"""
        
        for i in range(1, 19+1):
            mcs.SubsystemID(i)
        self.assertRaises(ValueError, mcs.SubsystemID, 0)
        self.assertRaises(ValueError, mcs.SubsystemID, 20)
        
    def test_cid_limits(self):
        """Test valid command ID values"""
        
        for i in range(0, 41+1):
            mcs.CommandID(i)
        self.assertRaises(ValueError, mcs.CommandID, 42)
        
    def test_mode_limits(self):
        """Test valid observing mode values"""
        
        for i in range(1, 9+1):
            mcs.ObservingMode(i)
        self.assertRaises(ValueError, mcs.ObservingMode, 0)
        self.assertRaises(ValueError, mcs.ObservingMode, 10)
        
    def test_pointing_correction(self):
        """Test the pointing correction function"""
        
        az = 63.4
        el = 34.2
        
        # No rotation
        theta = 0.0
        phi = 0.0
        psi = 0.0
        azP, elP = mcs.apply_pointing_correction(az, el, theta, phi, psi, degrees=True)
        self.assertAlmostEqual(azP, az, 2)
        self.assertAlmostEqual(elP, el, 2)
        
        # Azimuth only
        theta = 0.0
        phi = 0.0
        psi = 1.0
        azP, elP = mcs.apply_pointing_correction(az, el, theta, phi, psi, degrees=True)
        self.assertAlmostEqual(azP, az-1.0, 2)
        self.assertAlmostEqual(elP, el, 2)
        
        # Something random
        theta = 23.0
        phi = 10.0
        psi = 1.5
        azP, elP = mcs.apply_pointing_correction(az, el, theta, phi, psi, degrees=True)
        self.assertAlmostEqual(azP, 62.40, 2)
        self.assertAlmostEqual(elP, 34.37, 2)
        
        # Something else random (from an older version of LSL)
        az = 45.0
        el = 30.0
        theta = 3.0
        phi = 4.0
        psi = 5.0
        azP, elP = mcs.apply_pointing_correction(az, el, theta, phi, psi, degrees=True)
        self.assertAlmostEqual(azP, 40.117, 3)
        self.assertAlmostEqual(elP, 30.180, 3)
        
        # Something else random (from an older version of LSL)
        theta = 93.0
        phi = -4.0
        psi = 5.0
        azP, elP = mcs.apply_pointing_correction(az, el, theta, phi, psi, degrees=True)
        self.assertAlmostEqual(azP, 47.346, 3)
        self.assertAlmostEqual(elP, 33.702, 3)

    
class mcs_test_suite(unittest.TestSuite):
    """A unittest.TestSuite class which contains all of the lsl.common.mcs
    module unit tests."""
    
    def __init__(self):
        unittest.TestSuite.__init__(self)
        
        loader = unittest.TestLoader()
        self.addTests(loader.loadTestsFromTestCase(mcs_tests))        
        
        
if __name__ == '__main__':
    unittest.main()
