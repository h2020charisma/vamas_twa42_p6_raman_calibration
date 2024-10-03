# + tags=["parameters"]
upstream = ["templates_load","templates_read"]
product = None
config_root = None
neon_tag = None
si_tag = None
pst_tag = None
test_tags = None
fit_peaks = None
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

noise_factor = 1.5


def calibrate_x(op,laser_wl,spe_neon,spe_sil,find_kw={"wlen": 200, "width": 1},fit_peaks_kw = {}):
    
    calmodel = CalibrationModel.calibration_model_factory(
        laser_wl,
        spe_neon,
        spe_sil,
        neon_wl=rc2const.NEON_WL[laser_wl],
        find_kw=find_kw,
        fit_peaks_kw=fit_peaks_kw,
        should_fit=fit_peaks,
        prominence_coeff = 3
    )    
    assert len(calmodel.components) == 2
    # model_ne = calmodel.components[0]
    model_si = calmodel.components[1]  

    Path(os.path.join(product["data"],op)).mkdir(parents=True, exist_ok=True)
    model_si.peaks.to_csv(os.path.join(product["data"],op,"peaks.csv"),index=False)
    
    spe_sil_calib = apply_calibration_x(calmodel,spe_sil,spe_units="cm-1")

    find_kw = dict(sharpening=None)
    diff = []
    sname = []
    for spe in [spe_sil,spe_sil_calib]:
        spe_pos_dict = spe.fit_peak_positions(center_err_threshold=10, 
                                    find_peaks_kw=find_kw,  fit_peaks_kw=fit_peaks_kw)  # type: ignore 
        x_spe,x_reference,x_distance,df = rc2utils.match_peaks(spe_pos_dict, model_si.ref)
        if x_spe != None and len(x_spe)>0:
            sum_of_differences = np.sum(np.abs(x_spe - x_reference)) / len(x_spe)
        else:
            sum_of_differences = None
        #print("{}\tsum_of_differences {} {}".format(op,sum_of_differences, model_si.ref_units))
        diff.append(sum_of_differences)

    pd.DataFrame({"spectra" : ["Sil-original","Sil-calibrated"], "peak differences" : diff}).to_csv(os.path.join(product["data"],op,"differences.csv"),index=False)

    return calmodel

def apply_calibration_x(calmodel: CalibrationModel, old_spe: rc2.spectrum.Spectrum, spe_units="cm-1"):
    new_spe = old_spe
    model_units = spe_units
    for model in calmodel.components:
        if model.enabled:
            new_spe = model.process(new_spe, model_units, convert_back=False)
            model_units = model.model_units
    return new_spe


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
                spe_calib = apply_calibration_x(calmodel,spe,spe_units="cm-1")
            
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

    
