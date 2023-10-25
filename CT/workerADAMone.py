#!/usr/bin/python
import os
print(os.getenv("USER"))
print(os.getenv("SUDO_USER"))
#conda activate cellpose&&python D:\Carlos\Scripts\workerDECONVOLUTIOND106.py
#
######### Please add documentation
### This is for ADAMs project, it will be running the coimbinatorial imaging, using the fitting/drifting algorithm with PSFs and Flat Field Corrections sourced from Scope4 (Bogdans Microscope)
#################################################################
from multiprocessing import Pool, TimeoutError
import time,sys
import os,sys,numpy as np
# change this: 
master_analysis_folder = r'/home/cfg001/Desktop/wtc/CT'
sys.path.append(master_analysis_folder)
from ioMicro import *
#standard is 4, its number of colors +1 
ncols = 4

#change
psf_file = r'/home/cfg001/Desktop/wtc/CT/psfs/psf_750_Scope4_final.npy'
#/mnt/Ren-Imaging_NAS/Adam/E200_WTC11_WTday3__8_31_2023/AnalysisDeconvolve_CG
#/mnt/Ren-Imaging_NAS/Adam/One_by_one/E200_WTC11_WTday3__8_31_2023/AnalysisDevonvCG

save_folder = r'/mnt/Ren-Imaging_NAS/Adam/One_by_one/E200_WTC11_WTday3__8_31_2023/AnalysisDevonvCG'
#change to whatever Bogdan gives you
flat_field_fl = r'/home/cfg001/Desktop/wtc/CT/flat_field/Scope4_med_col_raw'

def compute_drift(save_folder,fov,all_flds,set_,redo=False):
    """
    save_folder where to save analyzed data
    fov - i.e. Conv_zscan_005.zarr
    all_flds - folders that contain eithger the MERFISH bits or control bits or smFISH
    set_ - an extra tag typically at the end of the folder to separate out different folders
    """
    #print(len(all_flds))
    #print(all_flds)
    gpu=True
    # defulat name of the drift file 
    drift_fl = save_folder+os.sep+'driftNew_'+fov.split('.')[0]+'--'+set_+'.pkl'
    
    iiref = None
    fl_ref = None
    previous_drift = {}
    if not os.path.exists(drift_fl) or redo:
        redo = True
    else:
        try:
            drifts_,all_flds_,fov_,fl_ref = pickle.load(open(drift_fl,'rb'))
            all_tags_ = np.array([os.path.basename(fld)for fld in all_flds_])
            all_tags = np.array([os.path.basename(fld)for fld in all_flds])
            iiref = np.argmin([np.sum(np.abs(drift[0]))for drift in drifts_])
            previous_drift = {tag:drift for drift,tag in zip(drifts_,all_tags_)}

            if not (len(all_tags_)==len(all_tags)):
                redo = True
            else:
                if not np.all(np.sort(all_tags_)==np.sort(all_tags)):
                    redo = True
        except:
            os.remove(drift_fl)
            redo=True
    if redo:
        fls = [fld+os.sep+fov for fld in all_flds]
        if fl_ref is None:
            fl_ref = fls[len(fls)//2]
        obj = None
        newdrifts = []
        all_fldsT = []
        for fl in tqdm(fls):
            fld = os.path.dirname(fl)
            tag = os.path.basename(fld)
            new_drift_info = previous_drift.get(tag,None)
            if new_drift_info is None:
                if obj is None:
                    obj = fine_drift(fl_ref,fl,sz_block=600)
                else:
                    obj.get_drift(fl_ref,fl)
                new_drift = -(obj.drft_minus+obj.drft_plus)/2
                new_drift_info = [new_drift,obj.drft_minus,obj.drft_plus,obj.drift,obj.pair_minus,obj.pair_plus]
            newdrifts.append(new_drift_info)
            all_fldsT.append(fld)
            pickle.dump([newdrifts,all_fldsT,fov,fl_ref],open(drift_fl,'wb'))
def compute_drift_features(save_folder,fov,all_flds,set_,redo=False,gpu=True):
    fls = [fld+os.sep+fov for fld in all_flds]
    for fl in fls:
    	#important to update here, not on ioMicro for the flat field, psf, etc...
        get_dapi_features(fl,save_folder,set_,gpu=gpu,im_med_fl = flat_field_fl+r'3.npz',
                    psf_fl = psf_file)
def main_do_compute_fits(save_folder,fld,fov,icol,save_fl,psf,old_method,icol_flat):
    '''
    Inputs: save_folder -> this is on the NAS,where the output is saved
    
    '''
    im_ = read_im(fld+os.sep+fov)
    im__ = np.array(im_[icol],dtype=np.float32)
    
    if old_method:
        ### previous method
        im_n = norm_slice(im__,s=30)
        #Xh = get_local_max(im_n,500,im_raw=im__,dic_psf=None,delta=1,delta_fit=3,dbscan=True,
        #      return_centers=False,mins=None,sigmaZ=1,sigmaXY=1.5)
        Xh = get_local_maxfast_tensor(im_n,th_fit=500,im_raw=im__,dic_psf=None,delta=1,delta_fit=3,sigmaZ=1,sigmaXY=1.5,gpu=False)
    else:
        
        fl_med = flat_field_fl+str(icol)+'.npy'

        
        if os.path.exists(fl_med):
            im_med = np.array(np.load(fl_med)['im'],dtype=np.float32)
            im_med = cv2.blur(im_med,(20,20))
            im__ = im__/im_med*np.median(im_med)
        try:
            Xh = get_local_max_tile(im__,th=3600,s_ = 500,pad=100,psf=psf,plt_val=None,snorm=30,gpu=True,
                                    deconv={'method':'wiener','beta':0.0001},
                                    delta=1,delta_fit=3,sigmaZ=1,sigmaXY=1.5)
        except:
            Xh = get_local_max_tile(im__,th=3600,s_ = 500,pad=100,psf=psf,plt_val=None,snorm=30,gpu=False,
                                    deconv={'method':'wiener','beta':0.0001},
                                    delta=1,delta_fit=3,sigmaZ=1,sigmaXY=1.5)
    np.savez_compressed(save_fl,Xh=Xh)
def compute_fits(save_folder,fov,all_flds,redo=False,ncols=ncols,
                psf_file = psf_file,try_mode=True,old_method=False,redefine_color=None):
    
    psf = np.load(psf_file)
    for ifld,fld in enumerate(tqdm(all_flds)):
        if redefine_color is not None:
            ncols = len(redefine_color[ifld])
        for icol in range(ncols-1):
            ### new method
            if redefine_color is None:
                icol_flat = icol
            else:
                #print("ifld is: "+str(ifld))
                #print("icol is: "+str(icol))
                icol_flat = redefine_color[ifld][icol]
            tag = os.path.basename(fld)
            save_fl = save_folder+os.sep+fov.split('.')[0]+'--'+tag+'--col'+str(icol)+'__Xhfits.npz'
            if not os.path.exists(save_fl) or redo:
                if try_mode:
                    try:
                        main_do_compute_fits(save_folder,fld,fov,icol,save_fl,psf,old_method,redefine_color)
                    except:
                        print("Failed",fld,fov,icol)
                else:
                    main_do_compute_fits(save_folder,fld,fov,icol,save_fl,psf,old_method,redefine_color)
                    
def compute_decoding(save_folder,fov,set_):
    dec = decoder_simple(save_folder,fov,set_)
    complete = dec.check_is_complete()
    if complete==0:
        dec.get_XH(fov,set_,ncols=ncols)#number of colors match
        dec.XH = dec.XH[dec.XH[:,-4]>0.25] ### keep the spots that are correlated with the expected PSF for 60X
        #this will likely change for
        dec.load_library(lib_fl = r'\\192.168.0.10\bbfishdc13\codebook_0_New_DCBB-300_MERFISH_encoding_2_21_2023.csv',nblanks=-1)
        dec.get_inters(dinstance_th=2,enforce_color=True)# enforce_color=False
        dec.get_icodes(nmin_bits=4,method = 'top4',norm_brightness=-1)
        
def main_f(set_ifov,try_mode=True):
    '''
    CHANGE PATH HERE
    '''
    #20230122_R120PVTS32RDNA for the data used in grant
    #r'\\merfish6\merfish6v2\DNA_FISH\20230212_R120PVTS32RDNABDNF\Analysis'
     ### save folder
    if not os.path.exists(save_folder): os.makedirs(save_folder)
    set__ = ''
   
    all_flds = []
    redefine_color = []
   
    
    
    #change to Adam's NAS, using H*DNA for the naming scheme
    all_flds_ = glob.glob(r'/mnt/Ren-Imaging_NAS/Adam/One_by_one/E200_WTC11_WTday3__8_31_2023/H*R*'+set__) ################################# modify for 3-col small tad 
    redefine_color += [[0,1,2,3]]*len(all_flds_) #### three signal color
    all_flds+=all_flds_
    
    all_flds_ = glob.glob(r'/mnt/Ren-Imaging_NAS/Adam/One_by_one/E200_WTC11_WTday3__8_31_2023/H0'+set__) ################################# modify for 3-col small tad 
    redefine_color += [[0,1,2,3]]*len(all_flds_) #### three signal color
    all_flds+=all_flds_
    
	'''
    ToDo : 
    1.Analyze sequential data (we should expand)and make sure it makes sense, see substructure
    2.
    '''

    # how to exclude an unwanted Hyb:
    #all_flds = [s for s in all_flds if "H38" not in s]
    
    
   
    set_,ifov = set_ifov
    all_flds = [fld.replace(set__,set_) for fld in all_flds]
    fovs_fl = save_folder+os.sep+'fovs__'+set_+'.npy'
    if not os.path.exists(fovs_fl):
        fls = glob.glob(all_flds[0]+os.sep+'*.zarr')
        fovs = [os.path.basename(fl) for fl in fls]
        np.save(fovs_fl,fovs)
    else:
        fovs = np.load(fovs_fl)
    if ifov<len(fovs):
        fov = fovs[ifov]
        
        print("Computing fitting on: "+str(fov))
        print(len(all_flds),all_flds)
        compute_fits(save_folder,fov,all_flds,redo=False,try_mode=try_mode,redefine_color=redefine_color)
        print("Computing drift on: "+str(fov))
        compute_drift_features(save_folder,fov,all_flds,set_,redo=False,gpu=True)
        #compute_drift(save_folder,fov,all_flds,set_,redo=False)
       
        #compute_decoding(save_folder,fov,set_)
        
    return set_ifov
if __name__ == '__main__':
    # start 4 worker processes
    items = [(set_,ifov)for set_ in ['']
                        for ifov in range(10000)]
    items.reverse()
    print(items)
    if True:
        with Pool(processes=8) as pool:
            print('starting pool')
            
            #try:
            #for i in range(0,201):
               #print("engaging with try mode...")
            result = pool.map(main_f,items)
            #except:
             #   print("failed at: " )

            
