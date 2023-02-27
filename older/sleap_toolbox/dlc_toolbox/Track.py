
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from matplotlib import gridspec

import scipy
import scipy.spatial
from scipy import signal
from scipy import ndimage
from scipy.optimize import linear_sum_assignment

import numpy as np
import os
import cv2
from tqdm import trange
from tqdm import tqdm

import sleap

import h5py

#

class Track():

    #
    def __init__(self, fname_slp):

        #
        self.verbose=False

        #
        self.fname_slp = fname_slp

        #
        self.slp = None

    def load_slp(self):

        self.slp = sleap.load_file(self.fname_slp)

    def slp_to_h5(self):

        fname_h5 = self.fname_slp[:-4] + ".h5"
        if self.slp is None:
            print("... slp file not loaded, loading now...")
            self.load_slp()
            print("... done loading slp")

        self.slp.export(fname_h5)

    def slp_to_npy(self):

        fname_h5 = self.fname_slp[:-4] + ".h5"
        if os.path.exists(fname_h5) == False:
            print("... h5 file missing, converting now...")
            self.slp_to_h5()
            print("... done loading h5")

        #
        hf = h5py.File(fname_h5, 'r')

        keys = hf.keys()
        group2 = hf.get('tracks')
        tracks = []
        for k in range(len(group2)):
            tracks.append(group2[k])

        tracks = np.array(tracks).transpose(3, 0, 2, 1)

        #
        fname_npy = self.fname_slp[:-4] + ".npy"
        np.save(fname_npy, tracks)

    def load_tracks(self):

        #
        fname_npy = self.fname_slp[:-4] + '.npy'
        if os.path.exists(fname_npy) == False:
            print("... npy missing, converting...")
            self.slp_to_npy()
            print("... done loading npy")

        #
        self.tracks = np.load(fname_npy)

        #
        self.tracks_centers = np.nanmean(
                                self.tracks,
                                axis=2)
        #
        self.get_track_spine_centers()

    def get_track_spine_centers(self):
        '''  This function returns single locations per animal
            with a focus on spine2, spine3, spine1 etc...
        '''
        #

        if self.no_huddle_features:
            fname_spine = self.fname_slp[:-4]+"_spine_nohuddle.npy"

        else:
            fname_spine = self.fname_slp[:-4]+"_spine.npy"

        #
        if os.path.exists(fname_spine)==False:

            self.tracks_spine = self.tracks_centers.copy()*0 + np.nan
            ids = [6,7,5,8,4,3,2,1,0]  # centred on spine2
            #points=[nose, lefteye, righteye, leftear,rightear, spine1, spine2, spine3,spine4]
            #         0       1        2        3         4      5        6        7      8

            #
            for n in trange(self.tracks.shape[0]):
                for a in range(self.tracks.shape[1]):
                    for id_ in ids:
                        if np.isnan(self.tracks[n,a,id_,0])==False:
                            self.tracks_spine[n,a]=self.tracks[n,a,id_]

                            break
            np.save(fname_spine, self.tracks_spine)
        else:
            self.tracks_spine = np.load(fname_spine)

    def make_tracks_chunks(self):
        ''' Function finds temporally continuous tracks
            Time-continuous-tracks
             Function breaks up continuous tracks that are too far apart;
             important for when ids jump around way too much
            Loop over the tcrs and check if jumps are too high to re-break track
        '''

        # break distances that are very large over single jumps
        # join by time
        self.time_cont_tracks = []
        for a in range(self.tracks_spine.shape[1]):
            track = self.tracks_spine[:,a]
            idx = np.where(np.isnan(track)==False)[0]
            diff = idx[1:]-idx[:-1]
            idx2 = np.where(diff>1)[0]

            # make track list
            self.time_cont_tracks.append([])

            # append first track
            self.time_cont_tracks[a].append([0,idx[idx2[0]]])

            # append all other tracks
            for i in range(1,idx2.shape[0],1):
                #if (idx[idx2[i]] - idx[idx2[i-1]+1])>0:
                self.time_cont_tracks[a].append([idx[idx2[i-1]+1],
                                idx[idx2[i]]])
                #else:
                #    print ("short: ", idx[idx2[i]] - idx[idx2[i-1]+1])

        # break by space
        thresh_dist = 100
        self.tracks_chunks = []
        for a in range(len(self.time_cont_tracks)):
            self.tracks_chunks.append([])
            while len(self.time_cont_tracks[a])>0:  #for k in range(len(self.tcrs[a])):
                times = self.time_cont_tracks[a][0]
                locs = self.tracks_spine[times[0]:times[1]+1, a]  # be careful to add +1
                dists = np.sqrt((locs[1:,0]-locs[:-1,0])**2+
                                (locs[1:,1]-locs[:-1,1])**2)
                idx = np.where(dists>=thresh_dist)[0]
                t = np.arange(times[0],times[1],1)
                if idx.shape[0]>0:
                    #if t[idx[0]]- t[0]>1:
                    self.tracks_chunks[a].append([t[0],t[idx[0]]])
                    for i in range(1,idx.shape[0],1):
                        #if (t[idx[i]]-t[idx[i-1]+1])>1:
                        self.tracks_chunks[a].append([t[idx[i-1]+1],
                                                              t[idx[i]]])

                    # add residual snippet at the end
                    if (t[idx[-1]]+1)<=times[1]: # and (t[idx[-1]]+1-times[1])>1:
                        self.tracks_chunks[a].append([t[idx[-1]]+1,
                                                      times[1]])

                else:
                    self.tracks_chunks[a].append(times.copy())

                # del
                del self.time_cont_tracks[a][0]


        # also make a similar array to tracks_spine that contains the mean confidence
        self.tracks_scores_mean = np.zeros((self.tracks_spine.shape[0],
                                                 self.tracks_spine.shape[1]),
                                                'float32')+np.nan
        for animal_id in range(len(self.tracks_chunks)):
            for c in range(len(self.tracks_chunks[animal_id])):
                chunk = self.tracks_chunks[animal_id][c]
                mean = self.scores[chunk[0]:chunk[1]+1,animal_id].mean(0)
                self.tracks_scores_mean[chunk[0]:chunk[1]+1,animal_id]= mean


    def del_single_chunks(self, min_chunk_len=2):

        for a in range(len(self.tracks_chunks)):
            chunks = np.array(self.tracks_chunks[a])

            #
            print (chunks.shape)
            lens = chunks[:,1]-chunks[:,0]

            #
            idx = np.where(lens<min_chunk_len)[0]
            # delete singles from the xy locs as well
            for id_ in range(idx.shape[0]):
                time = self.tracks_chunks[a][idx[id_]]
                self.tracks_spine[time[0]:time[1]+1, a]=np.nan

            #
            idx = np.where(lens>=min_chunk_len)[0]
            chunks = chunks[idx]
            self.tracks_chunks[a] = chunks
            print (len(self.tracks_chunks[a]))


    def get_scores(self):

        #
        fname_scores = self.fname_slp[:-4] + "_scores.npy"

        if os.path.exists(fname_scores) == False:
            print("... slp file loading...")
            self.load_slp()

            tracks = ['female', 'male', 'pup shaved', 'pup unshaved']
            self.scores = np.zeros((len(self.slp), 4), 'float32') + np.nan
            for n in trange(len(self.slp)):
                for a in range(len(self.slp[n])):
                    name = self.slp[n][a].track.name
                    idx = tracks.index(name)
                    self.scores[n, idx] = self.slp[n][a].score

            np.save(fname_scores, self.scores)

        else:
            self.scores = np.load(fname_scores)

    def plot_scores_distribution(self):
        width = 0.01
        for k in range(4):
            ax = plt.subplot(2, 2, k + 1)
            y = np.histogram(self.scores[:, k],
                             bins=np.arange(0, 1.02, width))
            plt.bar(y[1][:-1], y[0], width * .9)
            plt.title("animal " + str(k))
            plt.semilogy()
        plt.show()


    def find_nearest_forward(self, val, array2, window=1000.0):
        diff_temp = array2-val
        idx = np.where(diff_temp>0)[0]

        if idx.shape[0]==0 or diff_temp[idx[0]]>window:
            return 1E5, np.nan

        loc = idx[0]
        diff = diff_temp[idx[0]]
        return diff, loc

    #
    def find_nearest_backward(self, val, array2, window=1000.0):
        diff_temp = val-array2
        idx = np.where(diff_temp>0)[0]

        if idx.shape[0]==0 or diff_temp[idx[0]]>window:
            return 1E5, np.nan

        loc = idx[0]
        diff = diff_temp[idx[0]]
        return diff, loc

    #
    def get_chunk_info(self,
                       animal_id1,
                       t):


        ################### CURRENT ######################
        track_local = np.array(self.tracks_chunks[animal_id1])
        chunk_current = np.where(np.logical_and(t>=track_local[:,0], t<=track_local[:,1]))[0]
        times_current = track_local[chunk_current][0]
        locs_current = self.tracks_spine_fixed[times_current, animal_id1]

        if self.verbose:
            print ("Active animal:", animal_id1)
            print ("locs active; ", locs_current)
            print ("times active animal: ", times_current)

        return times_current, locs_current, chunk_current

    #
    def get_cost(self, t,
                times_active_animal,
                locs_active_animal,
                min_chunk_len,
                verbose=False):

        ''' Find distances between active animal chunk and other animals
            Notes: look for minimum distance to nearest
                - do not change very long tracks, sleap likely has them right

        '''
        cost = np.zeros(self.n_animals, 'float32')+1E5
        chunk_ids_compare = np.zeros(self.n_animals, 'float32')+np.nan
        for animal_id1 in range(self.n_animals):

            # grab chunk info
            track_local = np.array(self.tracks_chunks[animal_id1])

            ################### CURRENT ######################
            # if current track very long, make sure you don't change it
            chunk_id = np.where(np.logical_and(t>=track_local[:,0], t<=track_local[:,1]))[0]
            if self.verbose:
                print ("chunk id: ", chunk_id)
            if chunk_id.shape[0]>0:
                times_current = track_local[chunk_id][0]

                if times_current[1]-times_current[0]>self.time_threshold:
                    cost[animal_id1] = 1E5
                    continue

            ################# PREVIOUS #################
            chunk_ids = np.where(track_local[:,1]<t)[0]
            if self.verbose:
                print ("ANIMLA ID: ", animal_id1,
                        "prev hcunk id: ",
                       chunk_ids[-1],
                       " times: ", track_local[chunk_ids[-1]],
                       "locs : ", self.tracks_spine_fixed[track_local[chunk_ids[-1]],
                                                          animal_id1])
            # ensure we only look at sufficiently long track,s do not compare to singles/ or few
            z=-1
            while True:
                try:
                    chunk_id_prev = chunk_ids[z]
                    times_prev = track_local[chunk_id_prev]
                    if self.verbose:
                        print ("times prev: ", times_prev)
                    if (times_prev[1]-times_prev[0]+1)>=min_chunk_len:
                        locs_prev = self.tracks_spine_fixed[times_prev, animal_id1]
                        break
                except:
                    print ("broken: chunk_ids", chunk_ids)
                    chunk_id_prev = None
                    times_prev = np.array([-1E6,-1E6])
                    locs_prev = np.array([1E5,1E5],'float32')
                    break
                z-=1

            ################### NEXT ###################
            chunk_ids = np.where(track_local[:,0]>t)[0]
            if self.verbose:
                print ("ANIMLA ID: ", animal_id1,
                       "next chunk ids: ",
                       chunk_ids[0],
                       " times: ", track_local[chunk_ids[0]],
                          "locs : ", self.tracks_spine_fixed[track_local[chunk_ids[0]],
                          animal_id1])
            z=0
            while True:
                try:
                    chunk_id_next = chunk_ids[z]
                    times_next = track_local[chunk_id_next]
                    if (times_next[1]-times_next[0]+1)>=min_chunk_len:
                        locs_next = self.tracks_spine_fixed[times_next, animal_id1]
                        break
                except:
                    chunk_id_next = None
                    times_next = np.array([1E6,1E6])
                    locs_next = np.array([1E5,1E5],'float32')
                    break
                z+=1

            # make cost matrix
            # find distance between active chunk start and prev chunk:
            print ("DIFF to prev animal: times_prev[1] ",
                   times_prev[1])
            if times_active_animal[0]-times_prev[1]<self.time_threshold:
                c_prev = np.linalg.norm(locs_active_animal[0]-locs_prev[1])
            else:
                c_prev = 1E5

            #
            print ("DIFF to next animal times_next[0] ",
                   times_next[0])
            if times_next[0]-times_active_animal[1]<self.time_threshold:
                c_next = np.linalg.norm(locs_active_animal[1]-locs_next[0])
            else:
                c_next= 1E5

            #
            if verbose:
                print ("time: ", t)
                print ("animal id: ", animal_id1)
                #print ("  current: ", chunk_id, "times: ", times_current, " locs: ", locs_current)
                print ("  prev: ", chunk_id_prev, "times : ", times_prev, " locs: ", locs_prev)
                print ("  next: ", chunk_id_next, "times : ", times_next, " locs: ", locs_next)

                print ("times prev: ", times_prev)
                print ("cprev: ", c_prev, "  cnext: ", c_next)

            #
            if self.verbose:
                print ("animal ", animal_id1, " costs:  c_next, cprev ", c_next, c_prev)
            tot_cost = np.array([c_next,c_prev])
            cost[int(animal_id1)] = np.nanmin(tot_cost)

            if np.isnan(cost[int(animal_id1)]):
                if self.verbose:
                    print ("animal ", animal_id1, " has no self connection, replacing with 1E5")
                cost[int(animal_id1)]=1E5

        return cost

    #
    def swap_chunks(self,
                    correct_id,    # the correct assignemnt
                    animal_current, # the current assignemnt
                    times_current,
                    chunk_current,
                    verbose=False):


        if verbose:
            print ("swapping: ", correct_id, " with ", animal_current)
        ##########################################
        ##########################################
        ##########################################
        # hold memory
        temp_track = self.tracks_spine_fixed[times_current[0]:times_current[1]+1,
                                        animal_current].copy()
        #
        temp2_track = self.tracks_spine_fixed[times_current[0]:times_current[1]+1,
                                         correct_id].copy()

        #
        self.tracks_spine_fixed[times_current[0]:times_current[1]+1,
                           animal_current]= temp2_track

        # replace correct id with temp
        self.tracks_spine_fixed[times_current[0]:times_current[1]+1,
                           correct_id]= temp_track


        ##########################################
        ##########################################
        ##########################################
        #
        temp_chunk = times_current #self.tracks_chunks_fixed[animal_current][chunk_current].copy()
        if self.verbose:
            print ("***********************************************************************")
            print ("***********************SWAPPING ", animal_current ,  " WITH ", correct_id)
            print ("***********************************************************************")
            print ('track.tracks_chunks_fixed ', self.tracks_chunks_fixed[animal_current])
            print ("animal_current: ", animal_current)
            print ("chunk_current: ", chunk_current)

        #
        self.tracks_chunks_fixed[correct_id] = np.vstack((
                                                self.tracks_chunks_fixed[correct_id],
                                                temp_chunk))
        # reorder by time
        idx = np.argsort(self.tracks_chunks_fixed[correct_id][:,0])
        self.tracks_chunks_fixed[correct_id]= self.tracks_chunks_fixed[correct_id][idx]

        #
        if self.verbose:
            if correct_id == 2:
                print ("self.tracks_chunks_fixed[correct_id]",
                       self.tracks_chunks_fixed[correct_id][1333:],
                       "shoul dhave: ", temp_chunk)



        #
        self.tracks_chunks_fixed[animal_current] = np.delete(
                                                self.tracks_chunks_fixed[animal_current],
                                                chunk_current,
                                                axis=0)

    #
    def fix_tracks(self,
                   t,
                   t_end):

        #
        pbar = tqdm(total=(t_end-t))

        #
        animal_current = 0

        # make copies of fixed arrays
        self.tracks_chunks_fixed=[]
        for k in range(len(self.tracks_chunks)):
            self.tracks_chunks_fixed.append(np.array(self.tracks_chunks[k].copy()))

        #
        self.tracks_spine_fixed = self.tracks_spine.copy()

        #
        while True:  # <-------- need to advance in time slowly by indexing through each animal chunk
            pbar.update(t)

            # grab location for current chunk and animal being aanlyzed:
            times_current, locs_current, chunk_current = self.get_chunk_info(
                                                                        animal_current,
                                                                        t)
            if self.verbose:
                print ("###: t: ", t,
                       " animal current ", animal_current,
                       "  chunk current",  chunk_current,
                       " times current: ", times_current)

            # check to not change tracks that are very long:
            if (times_current[1]-times_current[0])<self.safe_chunk_length:

                # get cost:
                cost = self.get_cost(t, times_current,
                                        locs_current,
                                        self.min_chunk_len)

                if self.verbose:
                    print ("COST: ", cost)

                # closest swap attempt one animal at a time
                if np.min(cost)<self.max_distance_merge:

                    #
                    correct_id = np.argmin(cost)

                    # check if any data needs to be swapped
                    print ("INPUT TIMES CURRENT: ", times_current)

                    if correct_id!= animal_current:
                        self.swap_chunks(
                                        correct_id,     # the correct assignemnt
                                        animal_current, # the current assignemnt
                                        times_current,
                                        chunk_current)  # the times to swap

            ##################################################
            ######### FIND NEXT SECTION OF TRACK #############
            ##################################################
            # find next track start and ends
            temp = []
            for i in range(self.n_animals):
                # grab all tracks for each animal
                temp2 = np.array(self.tracks_chunks[i])

                # append all track starts that occur after current time;
                # TODO: this may skip tracks that start at the same time...
                next_chunk_time = np.where(temp2[:,0]>t)[0]

                #
                temp.append(temp2[next_chunk_time,0][0])

            # find the nearest start in time;
            t = np.min(temp)

            # select which animal the chunk belongs to
            animal_current = np.argmin(temp)

            #
            if self.verbose:
                print ('')
                print ('')
                print ("##########################################################################")
                print ("TIME: ", t, " active_animal: ", animal_current, " (temp: )", temp)


            if t>t_end:
                break

        pbar.close()


