# -*- coding: utf-8 -*

"""Module to set up path information for the LWA Software Library.  Two 
variables are defined by this module:  module and data.  `module' specifies
the absolute path to the module and `data' the abs. path to the data directory
where data files are stored."""

import os

__version__ = '0.1'
__revision__ = '$ Revision: 1 $'
__all__ = ['module', 'data']

this = os.path.dirname(__file__)
module = os.path.abspath(os.path.join(this, '..'))
data = os.path.join(module, 'data')