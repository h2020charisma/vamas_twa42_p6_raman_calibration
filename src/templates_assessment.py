# + tags=["parameters"]
upstream = ["templates_load","templates_read","templates_calibration"]
product = None
neon_tag = None
si_tag = None
pst_tag = None
# -

import hnswlib
import pandas as pd
import matplotlib.pyplot as plt
import os.path
from ramanchada2.spectrum import from_chada, Spectrum
from ramanchada2.protocols.calibration import CalibrationModel
import numpy as np
from pathlib import Path
from sklearn.cluster import SpectralBiclustering


_source = upstream["templates_load"]["data"]
_calibrated = upstream["templates_calibration"]["data"]



metadata = pd.read_hdf(upstream["templates_read"]["h5"], key="templates_read")
unique_optical_paths = metadata['optical_path'].unique()

color_map = {}
for index, string in enumerate(set([neon_tag,si_tag,pst_tag])):
    color_map[string] = plt.cm.tab10(index) 

trim_left = 100

dim = 1024*3
#p_original = hnswlib.Index(space = "cosine", dim=dim)
#p_original.init_index(max_elements = len(unique_optical_paths)*2, ef_construction = 10, M = 16)
#p_calibrated = hnswlib.Index(space = "cosine", dim=dim)
#p_calibrated.init_index(max_elements = len(unique_optical_paths)*2, ef_construction = 10, M = 16)
xlinspace = np.linspace(100,dim+100,num=dim)

ids_original = []
ids_calibrated = []

pdf_calibrated = []
pdf_original = []

from pynanomapper.clients.datamodel_simple import StudyRaman

for op in unique_optical_paths:
    op_meta = metadata.loc[metadata["optical_path"] == op]
    if not op_meta['enabled'].unique()[0]:
        continue
    provider = op_meta['provider'].unique()[0]
    wavelength = op_meta['wavelength'].unique()[0]    
    _path_source = os.path.join(_source,str(int(wavelength)),op)

    #calmodel = CalibrationModel.from_file(os.path.join(_path_source,"calibration.pkl"))    

    _path_calibrated = os.path.join(_calibrated,op)

    #will plot ycalibrated on right
    fig, ax = plt.subplots(1, 2, figsize=(15,2))    
    fig.suptitle("{} {} {}".format(op,provider,wavelength))
    #ax[].set_title("normalized")
    #ax2.set_title("calibrated")
    tag = pst_tag
    index = 0
    
    trim_left = 100
    ax[index].set_title(tag)
    tx = ax[index].twinx()
    try:
        spe = from_chada(os.path.join(_path_calibrated,"{}.cha".format(tag)),dataset="/calibrated")
        spe=spe.trim_axes(method='x-axis',boundaries=(trim_left,3500)) 
        spe.plot(label="{} calibrated".format(tag),ax=tx,color="#FF0000")
        y_copy = np.copy(spe.y)
        y_copy[y_copy < 0] = 0
        (spe,hist_dist,_) = StudyRaman.spectra2dist(Spectrum(spe.x,y_copy),xcrop = None,remove_baseline=False)
        pdf = hist_dist.pdf(xlinspace)

        pdf = np.max(y_copy)*pdf/max(pdf)
            #ax[index].plot(xlinspace,pdf,label="pdf",color="black")
            #pdf_calibrated.append(spe.y)
        pdf_calibrated.append(pdf)
        ids_calibrated.append("{}_{}".format(tag,op))
        
    except Exception as err:
        print(err)
    try:
        spe = from_chada(os.path.join(_path_source,"{}.cha".format(tag)),dataset="/raw")
        spe=spe.trim_axes(method='x-axis',boundaries=(trim_left,3500))  
        spe.plot(label=tag,ax=ax[index],color="#0000FF",linestyle='--')
            # play with low-pass filter (tapering/windowing function) to avoid getting noisy spectra after resampling
            #spe =  spe.resample_NUDFT_filter(x_range=(100,dim+100), xnew_bins=dim)
            #spe.y = spe.y / max(spe.y)
        y_copy = np.copy(spe.y)
        y_copy[y_copy < 0] = 0
        (spe,hist_dist,_) = StudyRaman.spectra2dist(Spectrum(spe.x,y_copy),xcrop = None,remove_baseline=False)
        pdf = hist_dist.pdf(xlinspace)
        pdf = np.max(y_copy)*pdf/max(pdf)
        pdf_original.append(pdf)
            #ax[index+1].plot(xlinspace,pdf,label="pdf",color=color_map[tag])
            #spe.plot(label=tag,ax=ax[index],color="black")
        ids_original.append("{}_{}".format(tag,op))
            #spe.spe_distribution()
    except Exception as err:
        print(err)


Path(product["hnswlib"]).mkdir(parents=True, exist_ok=True)
ids_original = pd.DataFrame(ids_original, columns=['unique_optical_paths'])
ids_original.to_csv(os.path.join(product["hnswlib"],"ids_original.csv"))
ids_calibrated = pd.DataFrame(ids_calibrated, columns=['unique_optical_paths'])
ids_calibrated.to_csv(os.path.join(product["hnswlib"],"ids_calibrated.csv"))

print(len(pdf_original),len(ids_original.index.values))
print(len(pdf_calibrated),len(ids_calibrated.index.values))

#p_original.add_items(pdf_original, ids_original.index.values)
#p_original.set_ef(50)
#p_original.save_index(os.path.join(product["hnswlib"],"normalized.cosine.index"))


#p_calibrated.add_items(pdf_calibrated, ids_calibrated.index.values)
#p_calibrated.set_ef(50)
#p_calibrated.save_index(os.path.join(product["hnswlib"],"calibrated.cosine.index"))


def plot_distances(pairwise_distances,identifiers):
    plt.figure(figsize=(8, 6))
    plt.imshow(pairwise_distances, cmap='YlGnBu', interpolation='nearest')
    plt.colorbar(label='Cosine similarity')
    plt.xticks(ticks=np.arange(len(identifiers)), labels=identifiers,rotation=90)
    plt.yticks(ticks=np.arange(len(identifiers)), labels=identifiers)
    plt.title('Cosine Distance Heatmap')
    plt.xlabel('Spectra')
    plt.ylabel('Spectra')
    plt.show()

def plot_biclustering(pairwise_distances, identifiers, title='Cosine similarity Heatmap',ax=None):
    
    # Perform biclustering
    model = SpectralBiclustering(n_clusters=(3, 3), method='log', random_state=0)
    model.fit(pairwise_distances)
    
    # Reorder the rows and columns based on the clustering
    fit_data = pairwise_distances[np.argsort(model.row_labels_)]
    fit_data = fit_data[:, np.argsort(model.column_labels_)]

    cax = ax.imshow(fit_data, cmap='YlGnBu', interpolation='nearest', vmin=0, vmax=1)
    plt.colorbar(cax, ax=ax, label='Cosine similarity')
    
    # Set ticks and labels
    ax.set_xticks(np.arange(len(identifiers)))
    ax.set_xticklabels(np.array(identifiers)[np.argsort(model.column_labels_)], rotation=90)
    ax.set_yticks(np.arange(len(identifiers)))
    ax.set_yticklabels(np.array(identifiers)[np.argsort(model.row_labels_)])
    
    # Set title and labels
    ax.set_title(title)

    ax.set_xlabel('Spectra')
    ax.set_ylabel('Spectra')
    

from sklearn.metrics.pairwise import cosine_similarity

#fig, ax = plt.subplots(len(pdf_original), 1, figsize=(15,2*len(pdf_original)))    
#for index,pdf in enumerate(pdf_original):
#    ax[index].plot(xlinspace,pdf,label=ids_original.index.values[index])
    #ax[index].set_title(ids_original[index])
#plt.legend()

tag = ["original","x-calibrated"]
ids = [ids_original,ids_calibrated]
fig, ax = plt.subplots(2, 2, figsize=(16,8))  
for index,pdf in enumerate([pdf_original, pdf_calibrated]):
    cos_sim_matrix =  cosine_similarity(pdf)
    upper_tri_indices = np.triu_indices_from(cos_sim_matrix, k=1)
    cos_sim_values = cos_sim_matrix[upper_tri_indices]
    # Step 3: Plot the distribution
    ax[index,0].hist(cos_sim_values, bins=10, color='blue', edgecolor='black')
    plt.title('Distribution of Cosine Similarities ({} spectra)'.format(tag[index]))
    plt.xlabel('Cosine Similarity')
    plt.ylabel('Frequency')
    plot_biclustering(cos_sim_matrix, ids[index]['unique_optical_paths'].values,title="Cosine similarity {} spectra".format(tag[index]),ax=ax[index,1])
    ax[index,0].set_title("{} [{:.2f}|{:.2f}|{:.2f}]".format("Cosine similarity histogram", np.min(cos_sim_matrix), np.mean(cos_sim_matrix), np.max(cos_sim_matrix)))
plt.show()