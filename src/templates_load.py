# + tags=["parameters"]
upstream = ["templates_read"]
product = None
config_root = None
neon_tag = None
si_tag = None
pst_tag = None
test_tags = None
# -


import pandas as pd
import ramanchada2 as rc2
import os.path
from pathlib import Path
import shutil
import matplotlib.pyplot as plt

metadata = pd.read_hdf(upstream["templates_read"]["h5"], key="templates_read")
unique_optical_paths = metadata['optical_path'].unique()

color_map = {}
for index, string in enumerate(set([neon_tag,si_tag,pst_tag])):
    color_map[string] = plt.cm.tab10(index) 

def load_spectrum(df,tag=None):
    row = 0 #tbd select based on SNR
    _file = os.path.join(config_root,df["filename"].iloc[row])
    return rc2.spectrum.from_local_file(_file),os.path.basename(_file)

def process_spectrum_baseline(spe,kwargs = {"niter" : 40 }):
    try:
        return spe.subtract_baseline_rc1_snip(**kwargs)        
    except Exception as err:
        print(err)
        return spe

def process_spectrum_normalize(spe,kwargs = {}):
    try:
        return spe.normalize(**kwargs)        
    except Exception as err:
        print(err)
        return spe

def read_tag(op_meta,tag, _path, boundaries=None, baseline=False, normalize = False, trim_left = 100):    
    pst_meta = op_meta.loc[op_meta["sample"]==tag]
    if pst_meta.shape[0] > 0:
        spe,_ = load_spectrum(pst_meta,tag)
        file_path = os.path.join(_path,"{}.cha".format(tag))
        if os.path.exists(file_path):
            os.remove(file_path)        
        spe.write_cha(file_path,dataset = "/raw")
        if boundaries is None:
            spe = spe.trim_axes(method='x-axis',boundaries=(trim_left,max(spe.x)))
        else:
            spe = spe.trim_axes(method='x-axis',boundaries=boundaries)
        if baseline:
            spe = process_spectrum_baseline(spe)
            spe.write_cha(file_path,dataset = "/baseline")        
        if normalize:
            spe = process_spectrum_normalize(spe)
            spe.write_cha(file_path,dataset = "/normalized")    
        return spe
    return None            

trim_left = 100
for op in unique_optical_paths:
    op_meta = metadata.loc[metadata["optical_path"] == op]
    if not op_meta['enabled'].unique()[0]:
        continue
    provider = op_meta['provider'].unique()[0]
    wavelength = op_meta['wavelength'].unique()[0]
    neon_meta = op_meta.loc[op_meta["sample"]==neon_tag]
    if neon_meta.shape[0] == 0:
        print(op,"No Neon")
        continue

    si_meta = op_meta.loc[op_meta["sample"]==si_tag]
    if si_meta.shape[0] == 0:
        print(op,"No Si")
        continue

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15,2))    
    fig.suptitle("{} {} {}".format(op,provider,wavelength))
    _path = os.path.join(product["data"],str(int(wavelength)))
    Path(_path).mkdir(parents=True, exist_ok=True)
    _path = os.path.join(product["data"],str(int(wavelength)),op)
    Path(_path).mkdir(parents=True, exist_ok=True)

    spe_neon, _file = load_spectrum(neon_meta,neon_tag)
    file_path = os.path.join(_path,"{}.cha".format(neon_tag))
    if os.path.exists(file_path):
        os.remove(file_path)            
    if min(spe_neon.x)<0:
        spe_neon = spe_neon.trim_axes(method='x-axis',boundaries=(trim_left,max(spe_neon.x)))  
        print(max(spe_neon.x))  
    spe_neon.write_cha(file_path,dataset = "/raw")

    try:
        spe_neon = process_spectrum_baseline(spe_neon)        
        spe_neon.write_cha(file_path,dataset = "/baseline")
    except Exception as err:
        print(err)
    try:
        spe_neon = process_spectrum_normalize(spe_neon)
        spe_neon.write_cha(file_path,dataset = "/normalized")
    except Exception as err:
        print(err)

    spe_neon.plot(label="Neon {}".format(_file),ax=ax1,color=color_map[neon_tag])

    for tag in [si_tag,pst_tag]:
        boundaries = None if tag==pst_tag else (520.45-200,520.45+200)
        spe = read_tag(op_meta,tag,_path,boundaries,baseline=True, normalize = True,trim_left=trim_left)
        if spe is not None:
            spe.plot(label=tag,ax=ax2,color=color_map[tag])

    for tag in test_tags.split(","):
        spe = read_tag(op_meta,tag,_path,boundaries=None,baseline=True, normalize = True,trim_left=trim_left)
        if spe is not None:
            spe.plot(label=tag,ax=ax2,color="#AAAAAA")

    ax1.set_title(neon_tag)
    ax2.set_title("")




