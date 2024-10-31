# + tags=["parameters"]
upstream = ["templates_load","templates_read"]
product = None
config_root = None
neon_tag = None
si_tag = None
pst_tag = None
test_tags = None
fit_ne_peaks = None
# -

import os.path
import glob
import pandas as pd
from ramanchada2.protocols.calibration import CalibrationModel
import ramanchada2.misc.constants  as rc2const
import ramanchada2 as rc2
from ramanchada2.spectrum import from_chada
import matplotlib.pyplot as plt
import ramanchada2.misc.utils as rc2utils
import numpy as np
from pathlib import Path
import traceback
from IPython.display import display

noise_factor = 1.5

def find_peaks(spe_test,profile="Gaussian"):
    find_kw={"wlen": 200, "width": 1, "sharpening" : None}
    find_kw["prominence"] = spe_test.y_noise_MAD() * 3
    cand = spe_test.find_peak_multipeak(**find_kw)
    fit_kw = {}
    return spe_test.fit_peak_multimodel(profile=profile,candidates=cand, **fit_kw ,no_fit=False) 

def calibrate_x(op,laser_wl,spe_neon,spe_sil,find_kw={"wlen": 200, "width": 1},fit_peaks_kw = {}):
    calmodel = None

    spe_neon.plot()
    try:
        calmodel = CalibrationModel.calibration_model_factory(
            laser_wl,
            spe_neon,
            spe_sil,
            neon_wl= rc2const.NEON_WL[laser_wl],
            find_kw={"wlen": 200, "width": 1},
            fit_peaks_kw={},
            should_fit=fit_ne_peaks,
            match_method="cluster"  # "assignment"
        )
    except Exception as err:
        traceback.print_exc()
   
   
    except Exception as err:
        traceback.print_exc()

    assert len(calmodel.components) == 2
    model_neon = calmodel.components[0]
    model_si = calmodel.components[1]  

    fig, ax = plt.subplots(1,1)
    model_neon.model.plot(ax=ax)

    Path(os.path.join(product["data"],op)).mkdir(parents=True, exist_ok=True)
    model_si.peaks.to_csv(os.path.join(product["data"],op,"peaks.csv"),index=False)
    
    spe_sil_calib = calmodel.apply_calibration_x(spe_sil,spe_units="cm-1")

    find_kw={"wlen": 200, "width": 1}
    diff = []
    sname = []
    for spe in [spe_sil,spe_sil_calib]:
        fitres = find_peaks(spe,profile="Pearson4")
        df = fitres.to_dataframe_peaks().sort_values(by="height",ascending=False)
        display(df.head(1))
        si_peak_found = df.iloc[0]["center"]
        print("{}\tdifferences {} {}".format(op,si_peak_found-520.45, model_si.ref_units))
        diff.append(si_peak_found-520.45)

    pd.DataFrame({"spectra" : ["Sil-original","Sil-calibrated"], "peak differences" : diff}).to_csv(os.path.join(product["data"],op,"differences.csv"),index=False)

    return calmodel




Path(product["data"]).mkdir(parents=True, exist_ok=True)
metadata = pd.read_hdf(upstream["templates_read"]["h5"], key="templates_read")
unique_optical_paths = metadata['optical_path'].unique()
source = upstream["templates_load"]["data"]
output = product["data"]

for op in unique_optical_paths:
    #if op!="Zo785_785_":
    #    continue
    #print(op)    
    op_meta = metadata.loc[metadata["optical_path"] == op]
    if not op_meta['enabled'].unique()[0]:
        continue
    #else:
    #    print(">>>",op,op_meta['enabled'].unique())
    wavelength = op_meta['wavelength'].unique()[0]
    _path_source = os.path.join(source,str(int(wavelength)),op)
    _path_output = os.path.join(output,op)
    Path(_path_output).mkdir(parents=True, exist_ok=True)
    
    try:
        neon_file = os.path.join(_path_source,"{}.cha".format(neon_tag))
        assert(os.path.exists(neon_file))
        spe_neon = from_chada(neon_file,dataset="/normalized")
        si_file = os.path.join(_path_source,"{}.cha".format(si_tag))
        assert(os.path.exists(si_file))
        spe_sil = from_chada(si_file,dataset="/normalized")

        calmodel = calibrate_x(op,wavelength,spe_neon,spe_sil)
        calmodel.save(os.path.join(_path_source,"calibration.pkl"))   
        #print(calmodel)
        tags = [si_tag,pst_tag]+test_tags.split(",")
        fig, axes = plt.subplots(len(tags)+1,1, figsize=(15,8))  
        fig.suptitle(op)   
        calmodel.plot(ax=axes[0])      
        axes[0].set_title("Neon")    
        for index,tag in enumerate(tags):
            try:
                spe = from_chada(os.path.join(_path_source,"{}.cha".format(tag)),dataset="/raw")
                spe.plot(label=f"{tag} original",ax=axes[index+1])
                spe_calib = calmodel.apply_calibration_x(spe,spe_units="cm-1")
            
                spe_calib.plot(ax=axes[index+1],label=f"{tag} calibrated")
                    
                #axes[index+1].set_title(tag)
                file_path = os.path.join(_path_output,"{}.cha".format(tag))
                if os.path.exists(file_path):
                    os.remove(file_path)            
                spe_calib.write_cha(file_path,dataset="/calibrated")
            except Exception as err:
                print(op,err)        
    except Exception as err:
        print(op,err)
    #break

    
