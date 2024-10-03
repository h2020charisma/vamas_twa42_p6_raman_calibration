# + tags=["parameters"]
upstream = ["read_metadata"]
product = None
config_root = None
config_root_output = None
data_folders = None
# -

from fuzzywuzzy import fuzz
import re
import pandas as pd
from ramanchada2 import spectrum
import os 

tags = { '785nm':"wavelength", 
        '532nm':"wavelength", 
        '785':"wavelength", 
        '532':"wavelength", 
        '405':"wavelength", 
        '514':"wavelength", 
        '150mW':"laser_power",
        '327mW':"laser_power",
        '(200mW)':"laser_power",      
        '20%':"laser_power_percent",   
        '050':"laser_power_percent",  
        '075':"laser_power_percent",  
        '005':"laser_power_percent",  
        '025':"laser_power_percent",  
          '150ms' : "acquisition_time",
          '150msx5ac' : "acquisition_time",
          '10min' : "acquisition_time",
          '5s' : "acquisition_time",
          'Probe': "probe", 
          '20x': "probe", 
          '1': "replicate",
          '2': "replicate",
          '3': "replicate",
          '4': "replicate",
         '5': "replicate",
         'position 1': "replicate",
         'txt' : "extension",
         'Neon' : 'sample',
         'Ti' : 'sample',
         'nCal' : 'sample',
         'sCal' : 'sample',
         'Si' : 'sample',
         'S1' : 'sample',
         'S0B' : 'sample',
         'PST' : 'sample',
         'LED' : 'sample',
         'NIR' : 'sample',
         'OP01' : "optical_path"
         }

_lookup = {
    "Original file" : "Original file",
    "laser_wavelength" : "wavelength",
    "Laser Wavelength" : "wavelength",
    "wl" : "wavelength",
    "model" : "instrument",
    "title" : "title",
    "device" : "instrument",
    "spectrometer" : "instrument",
    "Serial Number" : "instrument",
    "model" : "instrument",
    "c code" : "instrument",
    "laser_wavelength" : "wavelength",
    "laser_powerlevel" : "laser_power_percent",
    "intigration times(ms)":"acquisition_time",
    "integration times(ms)":"acquisition_time",
    "Integration Time":"acquisition_time",
    "integ_time" :  "acquisition_time",
    "time_stamp"  : "time_stamp", 
    "Timestamp" : "time_stamp" 
}


def fuzzy_match(vals,tags):
    parsed = {}
    parsed_similarity= {}
    for val in vals:
        similarity_score = None
        match = None
        for tag in tags:
            _tmp = fuzz.ratio(val,tag)
            if (similarity_score is None) or (similarity_score < _tmp):
                similarity_score =_tmp
                match = tags[tag]
        if not match in parsed:
            parsed[match]  = val
            parsed_similarity[match] = similarity_score
        else:
            if parsed_similarity[match] < similarity_score:
                parsed[match]  = val
                parsed_similarity[match] = similarity_score     
 
    try:
        if "wavelength" in parsed:
            parsed["wavelength"] = re.findall(r'\d+', parsed["wavelength"])[0]
    except Exception as err:
        print(err,parsed)

    if "extension" in parsed:
        del parsed["extension"]            
    return (parsed,parsed_similarity)


df=pd.read_excel(upstream["read_metadata"]["data"])
df.head()
#fuzzy_match([s for s in basename if s],tags)


for index, row in df.iterrows():
    filename_tags = row["basename"].replace(" ","_").split("_")
    #print(filename_tags,type(filename_tags))
    (parsed,parsed_similarity) = fuzzy_match(filename_tags,tags)
    for p in parsed:
        df.loc[index, p] = parsed[p]
    df.loc[index,"tags"] = ','.join(filename_tags)

df.to_excel(product["metadata_name"],index=False)

#folders = df["folder"].unique()
folders = []
basename = []
ext = []
keys = []
values = []
errs = []
for index, row in df.iterrows():
    file = os.path.join(row["folder"],'{}{}'.format(row["basename"],row["extension"]))
    _err = None
    try:
        spe = spectrum.from_local_file(file)
        for key in spe.meta.__root__:
            #print(key,spe.meta[key].encode('utf-8', errors='ignore'))
            try:
                keys.append(key)
                if isinstance(spe.meta[key], str):
                    values.append(spe.meta[key].encode('utf-8', errors='ignore').decode())
                else:
                    values.append(spe.meta[key])
                folders.append(row["folder"])
                basename.append(row["basename"])
                ext.append(row["extension"])
                errs.append("")        
            except Exception as x:
                print(key,x)
    except Exception as err:
        _err = err
        keys.append("")
        values.append("")
        folders.append(row["folder"])
        basename.append(row["basename"])
        ext.append(row["extension"])
        errs.append(_err)         

print(values)
print(len(keys),len(values),len(folders),len(basename),len(ext),len(errs))
df = pd.DataFrame({"folders" : folders,"basename" : basename,"extension" : ext,"keys" : keys,"values" : values, "errors" : errs})

df.head()

df.to_excel(product["metadata_file"],index=False)
