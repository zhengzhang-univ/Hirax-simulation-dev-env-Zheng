from __future__ import absolute_import, division, print_function, unicode_literals
from future.builtins import *  # noqa  pylint: disable=W0401, W0614
from future.builtins.disabled import *  # noqa  pylint: disable=W0401, W0614

# === End Python 2/3 compatibility

import os.path
import shutil
import warnings

import yaml

from caput import mpiutil

from drift.telescope import (
    cylinder,
    gmrt,
    focalplane,
    restrictedcylinder,
    exotic_cylinder,
)
from drift.core import beamtransfer

from drift.core import kltransform, doublekl
from drift.core import psestimation, psmc, crosspower
from drift.core import skymodel


teltype_dict = {
    "UnpolarisedCylinder": cylinder.UnpolarisedCylinderTelescope,
    "PolarisedCylinder": cylinder.PolarisedCylinderTelescope,
    "GMRT": gmrt.GmrtUnpolarised,
    "FocalPlane": focalplane.FocalPlaneArray,
    "RestrictedCylinder": restrictedcylinder.RestrictedCylinder,
    "RestrictedPolarisedCylinder": restrictedcylinder.RestrictedPolarisedCylinder,
    "RestrictedExtra": restrictedcylinder.RestrictedExtra,
    "GradientCylinder": exotic_cylinder.GradientCylinder,
}


## KLTransform configuration
kltype_dict = {"KLTransform": kltransform.KLTransform, "DoubleKL": doublekl.DoubleKL}


## Power spectrum estimation configuration
pstype_dict = {
    "Full": psestimation.PSExact,
    "MonteCarlo": psmc.PSMonteCarlo,
    "MonteCarloAlt": psmc.PSMonteCarloAlt,
    "Cross": crosspower.CrossPower,
}


def _resolve_class(clstype, clsdict, objtype=""):
    # If clstype is a dict, try and resolve the class from `module` and
    # `class` properties. If it's a string try and resolve the class from
    # either its name and a lookup dictionary.

    if isinstance(clstype, dict):
        # Lookup custom type

        modname = clstype["module"]
        clsname = clstype["class"]

        if "file" in clstype:
            import imp

            module = imp.load_source(modname, clstype["file"])
        else:
            import importlib

            module = importlib.import_module(modname)
        cls_ref = module.__dict__[clsname]
    #hirax_transfer.core

    elif clstype in clsdict:
        cls_ref = clsdict[clstype]
    else:
        raise Exception("Unsupported %s" % objtype)

    return cls_ref



configfile = "prod_params.yaml"

with open(configfile) as f:
    yconf = yaml.safe_load(f)
    
selfdirectory = yconf["config"]["output_directory"]

teltype = yconf["telescope"]["type"]

telclass = _resolve_class(teltype, teltype_dict, "telescope")

selftelescope = telclass.from_config(yconf["telescope"])

with open('selftelescope', 'wb') as tele_class_file:
    pickle.dump(selftelescope, tele_class_file)
    
## beam transfer generation
selfbeamtransfer = beamtransfer.BeamTransfer(
                selfdirectory + "/bt/", telescope=selftelescope
            )
            
with open('selfbt', 'wb') as bt_file:
    pickle.dump(selfbeamtransfer,bt_file)
            
selfbeamtransfer.generate(skip_svd=0)


## KL transform
selfkltransforms = {}
for klentry in yconf["kltransform"]:
    kltype = klentry["type"]
    klname = klentry["name"]
    klclass = _resolve_class(kltype, kltype_dict, "KL filter")
    kl = klclass.from_config(klentry, selfbeamtransfer, subdir=klname)
    selfkltransforms[klname] = kl
    
with open('selfkl', 'wb') as kl_file:
    pickle.dump(selfkltransforms,kl_file)

for klname, klobj in selfkltransforms.items():
    klobj.generate()

## psestimator
selfpsestimators = {}
for psentry in yconf["psfisher"]:
    pstype = psentry["type"]
    klname = psentry["klname"]
    psname = psentry["name"] if "name" in psentry else "ps"

    psclass = _resolve_class(pstype, pstype_dict, "PS estimator")

    if klname not in selfkltransforms:
        warnings.warn(
            "Desired KL object (name: %s) does not exist." % klname
        )
        selfpsestimators[psname] = None
    else:
        selfpsestimators[psname] = psclass.from_config(
            psentry, selfkltransforms[klname], subdir=psname
        )
        
for psname, psobj in selfpsestimators.items():
    psobj.generate()
    psobj.delbands()

