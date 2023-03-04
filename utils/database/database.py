import numpy as np
import os
from tqdm import trange
import parmap
import glob

from tqdm import tqdm
import sleap
import parmap
from itertools import combinations

#
import sys
sys.path.append("/home/cat/code/gerbil/utils") # go to parent dir

from track import track
from convert import convert
from ethogram import ethogram

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.cm as cm

import pandas as pd

#
class CohortProcessor():

    #
    def __init__(self, fname_spreadsheet):

        self.cohort_start_date = None
        self.cohort_end_date = None

        self.current_session = None

        self.fname_spreadsheet = fname_spreadsheet

        self.root_dir = os.path.split(self.fname_spreadsheet)[0]

        #self.list_methods()

    #
    def process_feature_track(self, fname_slp):

        if os.path.exists(fname_slp):

            fname_spine_out = fname_slp.replace('.slp',"_spine.npy")
            if os.path.exists(fname_spine_out):
                return

            t = track.Track(fname_slp)
            t.track_type = 'features'

            ###### parameters for computing body centroid #######
            t.use_dynamic_centroid = True   # True: alg. serches for the first non-nan value in this body order [2,3,1,0,4,5]
                                                 # - advantage: much more robust to lost features
                                                 # False: we fix the centroid to a specific body part
                                                 # - advantage less jitter for some applications
            t.centroid_body_id = [2]         # if centroid flag is False; we use this body part instead

            ##### run track fixer #######
            t.fix_all_tracks()

            ##### join spatially close but temporally distant chunks #####
            if False:
                #
                t.memory_interpolate_tracks_spine()

            ##### save the fixed spines will overwrite the previous/defatul spine values####
            t.save_centroid()


    def process_huddle_track(self, fname_slp,
                             fix_track_flag,
                             interpolate_flag):

        text = '_spine'
        if fix_track_flag:
           text = text + "_fixed"
        if interpolate_flag:
           text = text + "_interpolated"

        #
        fname_out = os.path.join(fname_slp[:-4]+text+".npy")

        #
        if os.path.exists(fname_out):
            return

        #
        t = track.Track(fname_slp)
        t.fix_track_flag = fix_track_flag
        t.interpolate_flag = interpolate_flag

        #############################################
        ############# RUN TRACK FIXER ###############
        #############################################
        max_jump_allowed = 50,              # maximum distance that a gerbil can travel in 1 frame
        max_dist_to_join = 50,              # maximum distnace between 2 chunks that can safely be merged
        min_chunk_len = 25                  # shortest duration of

        t.fix_huddles(max_jump_allowed,
                          max_dist_to_join,
                          min_chunk_len)

        ##################################################
        ################# RUN HUDDLE FIXER ###############
        ##################################################

        #
        fps = 24
        t.max_distance_huddle = 100                   # how far away we can merge huddles together (pixels)
        t.max_time_to_join_huddle = fps*120            # how far in time can we merge huddle chunks (seconds x frames)
        t.min_huddle_time = 120*fps                     # minimum huddle duration in seconds
        t.memory_interpolate_huddle()

        ##################################################
        ############## SAVE FIXED TRACKS #################
        ##################################################

        ##### save the fixed spines will overwrite the previous/defatul spine values####
        t.save_centroid()

        #
        t.save_updated_huddle_tracks(fname_out)

    #
    def remove_huddles_from_feature_tracks(self):

        #
        #self.root_dir_features = os.path.split(self.fname_spreadsheet)[0],
                                              #          'huddles')

        #
        fnames_slp_huddle = []
        fnames_slp_features = []
        found = 0
        for k in range(self.fnames_slp.shape[0]):
            fname_huddle = os.path.join(self.root_dir,
                                 'huddles',
							     self.fnames_slp[k][0]).replace('.mp4','_'+self.NN_type[k][0])+"_huddle_spine_fixed_interpolated.npy"

            fname_features = os.path.join(self.root_dir,
                                 'features',
							     self.fnames_slp[k][0]).replace('.mp4','_'+self.NN_type[k][0])+"_spine.npy"

            #
            if os.path.exists(fname_features) and os.path.exists(fname_features):
                fnames_slp_huddle.append(fname_huddle)
                fnames_slp_features.append(fname_features)
                found+=1
            else:
                pass
                #print ("missing file: ", self.fnames_slp[k][0])

        print ("# file pairs found: ", found, " (if less  than above, please check missing)")

        #
        fnames_all = list(zip(fnames_slp_features,fnames_slp_huddle))

        if self.parallel:
            parmap.map(self.remove_huddles,
                       fnames_all,
                       pm_processes=self.n_cores,
                       pm_pbar = True)
        else:
            for fnames in tqdm(fnames_all):
                self.remove_huddles(fnames)


    def remove_huddles(self,fnames):

        fname_features, fname_huddles = fnames[0], fnames[1]

        #
        huddles = np.load(fname_huddles)
        features = np.load(fname_features)

        #
        for k in range(huddles.shape[0]):

            h_locs = huddles[k]
            
            for h_loc in h_locs:
                
                if np.isnan(h_loc[0]):
                    continue
                #print (h_loc)

                f_loc = features[k]
                #print ("h_loc: ", h_loc.shape, "  f_loc: ", f_loc.shape)

                dists = np.linalg.norm(f_loc-h_loc,axis=1)
                #print ("dists: ", dists)

                # set
                idx = np.where(dists<=self.huddle_min_distance)
                #print ("idx: ", idx)
                features[k,idx]=np.nan

        fname_out = fname_features.replace('.npy','_nohuddle.npy')
        np.save(fname_out, features)


    #
    def preprocess_huddle_tracks(self):

        #
        self.root_dir_features = os.path.join(os.path.split(self.fname_spreadsheet)[0],
                                              'huddles')

        #
        fnames_slp = []
        for k in range(self.fnames_slp.shape[0]):
            fname = os.path.join(self.root_dir_features,
							     self.fnames_slp[k][0]).replace('.mp4','_'+self.NN_type[k][0])+"_huddle.slp"
            #
            if os.path.exists(fname):
                fnames_slp.append(fname)

        #
        if self.parallel:
            parmap.map(self.process_huddle_track,
                       fnames_slp,
                       self.fix_track_flag,
                       self.interpolate_flag,
                       pm_processes=self.n_cores,
                       pm_pbar = True)
        else:
            for fname_slp in tqdm(fnames_slp):
                self.process_huddle_track(fname_slp,
											self.fix_track_flag,
											self.interpolate_flag,)

    #
    def preprocess_feature_tracks(self):

        #
        self.root_dir_features = os.path.join(os.path.split(self.fname_spreadsheet)[0],
                                              'features')

        #
        fnames_slp = []
        for k in range(self.fnames_slp.shape[0]):
            fname = os.path.join(self.root_dir_features,self.fnames_slp[k][0]).replace(
                                    '.mp4','_'+self.NN_type[k][0])+".slp"
            if os.path.exists(fname):
                fnames_slp.append(fname)


        #
        if self.parallel:
            parmap.map(self.process_feature_track,
                   fnames_slp,
                   pm_processes=self.n_cores,
                   pm_pbar = True)
        else:
            for fname_slp in tqdm(fnames_slp):
                self.process_feature_track(fname_slp)

        #


    #
    def load_database(self):


        pd.set_option('display.max_rows',500)
        pd.set_option('display.max_columns',504)
        pd.set_option('display.width',1000)

        df = pd.read_excel(self.fname_spreadsheet, engine='openpyxl')
        df.style.applymap(lambda x:'white-space:nowrap')
        print ("DF: ", df.head() )

        ###################################################################
        ########## SAVE FILENAMES WITH 6 ANIMALS AND NN TYPES #############
        ###################################################################
        #
        print ("Loading only recordings with 6 animals...")
        self.n_gerbils = df.loc[:,'# of Gerbils']
        #print ("# of gerbils: ", self.n_gerbils)

        #
        self.PDays = df.loc[:,'Dev Day']

        #
        self.Start_times = df.loc[:,'Start time']

        #
        idx = np.where(self.n_gerbils==6)[0]
        print (" ... total # : ", idx.shape[0], " / ", self.n_gerbils.shape[0])

        fnames = df.loc[:,'Filename']
        self.fnames_slp = np.vstack(fnames.iloc[idx].tolist())

        #
        self.NN_type = np.vstack(df.loc[:,'NN Type'].iloc[idx].tolist())


    #
    def list_methods(self):
        method_list = [func for func in dir(self)
                       if callable(getattr(self, func)) and
                       not func.startswith("__")]

        print ("Available methods: ",
               *method_list,
               sep='\n  ')


    #
    def compute_rectangle_occupancy(self,
                                 track_local,
                                 lower_left,
                                 upper_right):
        #
        idx = np.where(np.isnan(track_local.sum(1))==False)[0]
        track_local2 = track_local[idx]
        idx2 = np.where(np.all(np.logical_and(track_local2>=lower_left,
                                     track_local2 <= upper_right), axis=1))[0]
        #print (track_local2.shape, idx2.shape)

        return idx2.shape[0]/track_local.shape[0]*100

    #
    def get_rectangle_occupancy(self, a1):

        #
        res=[]
        lower_left = self.rect_coords[0]
        upper_right = self.rect_coords[1]

        #
        for k in trange(0,1500,1):
            self.track_id = k
            track = self.load_single_feature_spines()
            # if track is missing, skip it
            if track is None:
                res.append(0)
                continue

            #
            temp = self.compute_rectangle_occupancy(track.tracks_spine[:,a1],
                                                    lower_left,
                                                    upper_right)

            res.append(temp)

        res = np.array(res)
        print ("res: ", res.shape)

        self.res = res


    #
    def compute_circle_occupancy(self,
                                 track_local,
                                 centre,
                                 radius):
        #
        xx = track_local-centre
        idx = np.where(np.isnan(xx.sum(1))==False)[0]
        dists = np.linalg.norm(xx[idx],axis=1)
        idx = np.where(dists<=radius)[0]

        return idx.shape[0]/xx.shape[0]*100

    #
    def get_circle_occupancy(self, a1):

        res=[]
        centre = self.circle_coords[0]
        radius = np.linalg.norm(self.circle_coords[0]-self.circle_coords[1])

        #
        for k in trange(0,1500,1):
            self.track_id = k
            track = self.load_single_feature_spines()
            # if track is missing, skip it
            if track is None:
                res.append(0)
                continue

            #
            temp = self.compute_circle_occupancy(track.tracks_spine[:,a1],
                                                 centre,
                                                 radius)


            res.append(temp)

        res = np.array(res)
        #print ("res: ", res.shape)

        self.res = res

    def show_developmental_trajectories(self):

        #
        print (self.animal_ids)

        #
        d = []
        for animal_id in self.animal_ids:

            #
            #fname_in = os.path.join(self.root_dir,
            #                        self.behavior_name+"_"+str(animal_id)+'.npy').replace('(','[').replace(')',']')
            fname_in = os.path.join(self.root_dir,
                                     self.behavior_name+"_"+str(animal_id) +"_excludehuddles_"
                                     +str(self.exclude_huddles)+ '.npy').replace('(','[').replace(')',']')

            #
            temp = np.load(fname_in)
            d.append(temp)

        d = np.vstack(d)
        print (d.shape)
        print ("sums: ", np.nansum(d))

        #
        from sklearn import decomposition

        idx = np.where(np.isnan(d))
        d[idx]=0

        #
        pca = decomposition.PCA(n_components=3)
        X_pca = pca.fit_transform(d)

        print ("X_pca: ", X_pca.shape)
        clrs = ['black','blue','red','green','brown','pink','magenta','lightgreen','lightblue',
                'yellow','lightseagreen','orange','grey','cyan','teal','lawngreen']

        # removes days which have zero entries
        if self.remove_zeros:
            idx = np.where(d.sum(1)==0)
            print ("removing zeros: ", idx[0].shape)
            X_pca[idx]=np.nan

        #
        plt.figure()
        for k in range(0,X_pca.shape[0],temp.shape[0]):

            x = X_pca[k:k+temp.shape[0],0]
            y = X_pca[k:k+temp.shape[0],1]
            sizes = np.arange(1,10+temp.shape[0])*10


            idx = np.where(np.isnan(x)==False)
            x = x[idx]
            y = y[idx]
            sizes = sizes[idx]
            #print (idx)

            plt.scatter(x,
                        y,
                        label=str(self.animal_ids[k//temp.shape[0]]),
                        s=sizes,
                        c=clrs[k//temp.shape[0]])

            # connect lines
            plt.plot(x,
                     y,
                        c=clrs[k//temp.shape[0]])

        plt.xlabel("PC1")
        plt.ylabel("PC2")
        plt.title(self.behavior_name)
        plt.legend()
        plt.show()


    #
    def get_pairwise_interaction_time(self, a1, a2):

        names = ['female','male','pup1','pup2','pup3','pup4']
        self.animals_interacting = ''+names[self.animal_ids[0]] + " " + names[self.animal_ids[1]]


        res=[]
        for k in trange(0,1500,1):
            self.track_id = k
            track = self.load_single_feature_spines()

            # if track is missing, skip it
            if track is None:
                res.append(np.zeros((6,6))[a1,a2])
                continue

            #
            self.symmetric_matrices=False
            self.plotting=False
            temp = self.compute_pairwise_interactions(track)
            try:
                temp = temp[a1,a2]
            except:
                print ("Missing animal track...")
                temp = np.zeros((6,6))[a1,a2]

            res.append(temp)

        res = np.array(res)

        self.res = res

    #
    def format_behavior(self):

        #
        self.data = []
        for k in range(self.PDays.shape[0]):

            PDay = self.PDays[k]
            time = self.Start_times[k]
            self.data.append([int(PDay[1:]), time.hour, self.res[k]])

        #
        self.data = np.vstack(self.data)
        #print (self.data)

        # compute average per hour
        self.data_ave = []
        s = []
        s.append(self.data[0,2])
        for k in range(0,self.data.shape[0]-1,1):
            if self.data[k,1]==self.data[k+1,1]:
                s.append(self.data[k+1,2])
            else:
                temp = self.data[k]
                temp[2] = np.mean(s)
                self.data_ave.append(temp)
                s=[]

        self.data = np.vstack(self.data_ave)

    #
    def list_recordings(self):



        pass

    def compress_video(self):
        pass

    #
    def load_single_feature_spines(self):


        try:
            fname = os.path.join(os.path.split(self.fname_spreadsheet)[0],
                                     'features',
                                     self.fnames_slp[self.track_id][0].replace('.mp4','_'+self.NN_type[self.track_id][0]+".slp"))
        except:
            return None


        #
        t = track.Track(fname)
        t.fname=fname
        #
        if os.path.exists(fname)==False:
            return None

        #
        t.exclude_huddles = self.exclude_huddles
        t.get_track_spine_centers()

        return t

    def process_time(self):

        ''' Function that uses filename to generate metadata

            - generates Universal Dev Time from timestamp
            - generates Day vs. Nighttime label from timestamp
            - identifies the correct NN for the file

        '''

        #
        print ("current session: ", self.current_session)

    def set_roi(self):

        #
        global circle_coords, rect_coords
        global ax1, fig

        from matplotlib import pyplot as plt, patches

        fig, ax1 = plt.subplots(figsize=(13,10))
       # #line, = ax1.plot(x, y, 'o', picker=10)
        plt.ylim(0,700)

        #
        track_local = np.load(self.fname_slp_npy)
        print (track_local.shape)

        plt.imshow(self.video_frame,
                   aspect='auto')
        plt.plot(track_local[:,0,0],
                 track_local[:,0,1])
#
        plt.title("Left button: 1- centre; 2-radius\n "+
                   "Right button: 1- bottom left; 2-top right\n " +
                   "Centre button: exit")


        circle_coords=np.zeros((2,2))
        rect_coords=np.zeros((2,2))

        #
        def click_handler(event):
            global circle_coords, rect_coords
            global ax1, fig

            if event.button == 3:
                if rect_coords[0].sum()==0:
                    rect_coords[0] = [event.xdata, event.ydata]
                else:
                    rect_coords[1] = [event.xdata, event.ydata]
                #print("left-click!", circle_coords)
                # do something

            if event.button == 2:
                plt.close(fig)
                return

            #
            if event.button == 1:
                if circle_coords[0].sum()==0:
                    circle_coords[0] = [event.xdata, event.ydata]
                else:
                    circle_coords[1] = [event.xdata, event.ydata]

            if circle_coords[1].sum()>0:
                diff =  circle_coords[0]-circle_coords[1]

                dist = np.linalg.norm(diff)
                circle1 = patches.Circle(circle_coords[0],
                                         dist,
                                         color='r',
                                         alpha=.5)
                ax1.add_patch(circle1)
                fig.canvas.draw()
                fig.canvas.flush_events()
                #

            #
            if rect_coords[1].sum()>0:
                rect_coords = np.vstack(rect_coords)

                for k in range(2):
                    plt.plot([rect_coords[k][0], rect_coords[k][0]],
                             [rect_coords[0][1], rect_coords[1][1]],
                            '--',
                            c='red')

                for k in range(2):
                    plt.plot([rect_coords[0][0], rect_coords[1][0]],
                             [rect_coords[k][1], rect_coords[k][1]],
                            '--',
                            c='red')

                fig.canvas.draw()
                fig.canvas.flush_events()

                #


        #
        fig.canvas.mpl_connect('button_press_event', click_handler)

        #
        plt.show(block=True)

        #
        self.circle_coords=circle_coords
        self.rect_coords=rect_coords



    #
    def load_video(self):
        ''' Function that takes as input filename

        :return:
        '''

        import cv2

        #
        cap = cv2.VideoCapture(self.fname_video)

        while(cap.isOpened()):
            ret, frame = cap.read()

            break

        cap.release()
        cv2.destroyAllWindows()

        self.video_frame = frame

    #
    def detect_audio(self):
        pass

    #
    def compute_pairwise_interactions(self,track):

        #
        x_ticks=['female','male','pup1','pup2','pup3','pup4']


        self.distance_threshold = 250 # # of pixels away assume 1 pixel ~= 0.5mm -> 20cm
        time_window = 1*25 # no of seconds to consider
        self.smoothing_window = 3
        min_distance = 25 # number of frames window
        fps=24

        locs = track.tracks_spine.transpose(1,0,2)
        traces_23hrs = locs

        # COMPUTE PAIRWISE INTERACTIONS
        animals=np.arange(locs.shape[0])
        interactions = np.zeros((animals.shape[0],animals.shape[0]),'int32') + np.nan
        durations_matrix = np.zeros((animals.shape[0], animals.shape[0]),'int32') + np.nan

        ########################################################
        ########################################################
        ########################################################
        # loop over all pairwise combinations
        pair_interaction_times = []
        pairs1 = list(combinations(animals,2))
        #for pair in tqdm(pairs1, desc='pairwise computation'):
        for pair in pairs1:
            traces = []

            # smooth out traces;
            for k in pair:
                traces1=traces_23hrs[k].copy()
                traces1[:,0]=np.convolve(traces_23hrs[k,:,0], np.ones((self.smoothing_window,))/self.smoothing_window, mode='same')
                traces1[:,1]=np.convolve(traces_23hrs[k,:,1], np.ones((self.smoothing_window,))/self.smoothing_window, mode='same')
                traces1 = traces1
                traces.append(traces1)

            # COMPUTE PAIRWISE DISTANCES AND NEARBY TIMES POINTS
            idx_array = []
            diffs = np.sqrt((traces[0][:,0]-traces[1][:,0])**2+
                            (traces[0][:,1]-traces[1][:,1])**2)
            idx = np.where(diffs<self.distance_threshold)[0]

            # COMPUTE TOTAL TIME TOGETHER
            #print ("Pairwise: ", pair, idx.shape)
            durations_matrix[pair[0],pair[1]]=idx.shape[0]/fps

            # COMPUTE # OF INTERACTIONS;
            diffs_idx = idx[1:]-idx[:-1]
            idx2 = np.where(diffs_idx>5)[0]
            interactions[pair[0],pair[1]]=idx2.shape[0]

            # SAVE TIMES OF INTERACTION
            pair_interaction_times.append(idx)

        # SYMMETRIZE MATRICES
        if self.symmetric_matrices:
            for k in range(durations_matrix.shape[0]):
                for j in range(durations_matrix.shape[1]):
                    if np.isnan(durations_matrix[k,j])==False:
                        durations_matrix[j,k]=durations_matrix[k,j]
                        interactions[j,k]=interactions[k,j]


        # #################################################
        # ######### PLOT INTERACTIONS PAIRWISE ############
        # #################################################
        dur_matrix_percentage = durations_matrix/(locs.shape[1]/fps)*100

        if self.plotting:
            plt.figure()
            labelsize=14
            ax2=plt.subplot(1,1,1)
            im = plt.imshow(durations_matrix, cmap='viridis')

            #x_ticks=['female','male','pup1','pup2']
            plt.xticks(np.arange(locs.shape[0]),
                       x_ticks,rotation=15)
            plt.yticks(np.arange(locs.shape[0]),
                       x_ticks,rotation=75)
            plt.tick_params(labelsize=labelsize)

            cbar = plt.colorbar()
            cbar.set_label("time together (sec)", fontsize=labelsize)

            ##############################################
            ############ PLOT PAIRWISE DURATIONS ########
            #################################################
            plt.figure()
            ax2=plt.subplot(1,1,1)

            dur_matrix_percentage = durations_matrix/(locs.shape[1]/fps)*100
            plt.imshow(dur_matrix_percentage, cmap='viridis')

            #x_ticks=['female','male','pup1','pup2']
            plt.xticks(np.arange(locs.shape[0]),
                       x_ticks,rotation=15)
            plt.yticks(np.arange(locs.shape[0]),
                       x_ticks,rotation=75)
            plt.tick_params(labelsize=labelsize)

            cbar = plt.colorbar()
            cbar.set_label("time together (% of total recording)", fontsize=labelsize)
            #

            #
            plt.suptitle(os.path.split(track.fname)[1])


            plt.show()

        return dur_matrix_percentage
