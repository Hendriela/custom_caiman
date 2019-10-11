#!/usr/bin/env python
# -*- coding: utf-8 -*-
# author: Hendrik Heiser
# created on 11 October 2019

import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns


class PlaceCellFinder:
    """
    Class that holds all the data, parameters and results to perform place cell analysis.
    The analysis steps and major parameters are mainly adapted from Dombeck2007/2010, Hainmüller2018 and Koay2019.
    """
    def __init__(self, cnmf, params=None):
        """
        Constructor of the PCF class

        PlaceCellFinder objects are organized in two major parts:
        - Actual data like the raw cnmf object, dF/F traces or binned data is stored in individual attributes.
        - Initial analysis parameters or parameters that are calculated during the analysis pipeline are stored in the
          params dictionary.

        PCF objects have to be initialized with the raw calcium data (cnmf object) and can already be initialized with
        parameters in the params dictionary. Other parameters can be set later, and all other attributes are results
        from analysis steps and will be filled during the pipeline.

        :param cnmf: CNMF object that holds the raw calcium data
        :param params: dictionary that holds the pipeline's parameters. Can be initialized now or filled later.
        """
        self.cnmf = cnmf
        self.session = None
        self.session_trans = None
        self.behavior = None
        self.bin_frame_count = None
        self.bin_activity = None
        self.bin_avg_activity = None

        if params is not None:
            self.params = params
        else:
            self.params = {'frame_list': None,      # list of number of frames in every trial in this session
                           'trial_list': None,      # trial number of files that should be included in the analysis #TODO somehow get it to work automatically, change save organisation?
                           'trans_length': 0.5,     # minimum length in seconds of a significant transient
                           'n_bins': 100,           # number of bins per trial in which to group the dF/F traces
                           'bin_window_avg': 3,     # sliding window of bins (left and right) for trace smoothing
                           'bin_base': 0.25,        # fraction of lowest bins that are averaged for baseline calculation
                           'place_thresh': 0.25,    # threshold of being considered for place fields, calculated
                                                    # from difference between max and baseline dF/F
                           'min_bin_size': 10,      # minimum size in bins for a place field (should correspond to 15-20 cm)
                           'fluo_infield': 7,       # factor above which the mean DF/F in the place field should lie compared to outside the field
                           'trans_time': 0.2,       # fraction of the (unbinned!) signal while the mouse is located in
                                                    # the place field that should consist of significant transients
                           'n_splits': 10,          # segments the binned DF/F should be split into for bootstrapping. Has to be a divisor of n_bins

            # The following parameters are calculated during analysis and do not have to be set by user
                           'n_neuron': None,        # number of neurons that were detected in this session
                           'n_trial': None,         # number of trials in this session
                           'sigma': None,           # array[n_neuron x n_trials], noise level (from FWHM) of every trial
                           'bin_frame_count': None} # array[n_bins x n_trials], number of frames averaged in each bin



    def split_traces_into_trials(self):
        """
        First function to call in the "normal" pipeline.
        Takes raw, across-trial DF/F traces from the CNMF object and splits it into separate trials using the frame
        counts provided in frame_list (#todo get frame_list from trial file names).
        It returns a "session" list of all neurons. Each neuron itself is a list of 1D arrays that hold the DF/F trace
        for each trial in that session. "Session" can thus be indexed as session[number_neurons][number_trials].

        :return: Updated PCF object with the session list
        """
        if self.params['frame_list'] is not None:
            frame_list = self.params['frame_list']
            n_trials = len(frame_list)
        else:
            raise Exception('You have to provide frame_list before continuing the analysis!')
        n_neuron = self.cnmf.estimates.F_dff.shape[0]
        session = list(np.zeros(n_neuron))

        for neuron in range(n_neuron):
            curr_neuron = list(np.zeros(n_trials))  # initialize neuron-list
            session_trace = self.cnmf.estimates.F_dff[neuron]  # temp-save DF/F session trace of this neuron

            for trial in range(n_trials):
                # extract trace of the current trial from the whole session
                if len(session_trace) > frame_list[trial]:
                    trial_trace, session_trace = session_trace[:frame_list[trial]], session_trace[frame_list[trial]:]
                    curr_neuron[trial] = trial_trace  # save trial trace in this neuron's list
                elif len(session_trace) == frame_list[trial]:
                    curr_neuron[trial] = session_trace
                else:
                    print('Error in PlaceCellFinder.split_traces()')
            session[neuron] = curr_neuron  # save data from this neuron to the big session list

        self.session = session
        self.params['n_neuron'] = n_neuron
        self.params['n_trial'] = n_trials

        return self

    def create_transient_only_traces(self):
        """
        Takes the traces ordered by neuron and trial and modifies them into transient-only traces.
        Significant transients are detected using the full-width-half-maximum measurement of standard deviation (see
        Koay et al., 2019). The traces itself are left untouched, but all values outside of transients are set to 0.
        This is mainly useful for the place field criterion 3 (20% of time inside place field has to be transients).
        # Todo: implement the criterion described in Dombeck2007 and Zaremba2017 with negative and positive transients?
        The structure of the resulting list is the same as PCF.session (see split_traces_into_trials()).
        Additionally, the noise level sigma is saved for every neuron for each trial in params[sigma] as an array with
        the shape [n_neurons X n_trials] and can be indexed as such to retrieve noise levels for every trial.
        :return: Updated PCF object with the significant-transient-only session_trans list
        """
        session_trans = list(np.zeros(self.params['n_neuron']))
        self.params['sigma'] = np.zeros((self.params['n_neuron'], len(self.session_trans[0])))
        self.params['sigma'].fill(np.nan)
        for neuron in range(len(self.session_trans)):
            curr_neuron = self.session[neuron]
            for i in range(len(curr_neuron)):
                trial = curr_neuron[i]
                # get noise level of the data via FWHM
                sigma = self.get_noise_fwhm(trial)
                self.params['sigma'][neuron][i] = sigma     # save noise level of current trial in the params dict
                # get time points where the signal is more than 4x sigma (Koay et al., 2019)
                if sigma == 0:
                    idx = []
                else:
                    idx = np.where(trial >= self.params['trans_thresh'] * sigma)[0]
                # split indices into consecutive blocks
                blocks = np.split(idx, np.where(np.diff(idx) != 1)[0] + 1)
                # find blocks of >500 ms length (use frame rate in cnmf object) and merge them in one array
                duration = int(self.params['trans_length'] / (1 / self.cnmf.params.data['fr']))
                try:
                    transient_idx = np.concatenate([x for x in blocks if x.size >= duration])
                except ValueError:
                    transient_idx = []
                # create a transient-only trace of the raw calcium trace
                trans_only = trial.copy()
                select = np.in1d(range(trans_only.shape[0]), transient_idx) # create mask for trans-only indices
                trans_only[~select] = 0 # set everything outside of this mask to 0

                # add the transient only trace to the list
                session_trans[neuron][i] = trans_only

        # add the final data structure to the PCF object
        self.session_trans = session_trans

        return self

    def get_noise_fwhm(self, data):
        """
        Returns noise level as standard deviation (sigma) from a dataset using full-width-half-maximum
        (Koay et al. 2019). This method is less sensitive to long tails in the distribution (useful?).
        :param data: dataset in a 1D array that you need the noise level from
        :return: noise: float, sigma of given dataset
        """
        if np.all(data == 0): # catch trials without data
            sigma = 0
        else:
            plt.figure()
            x_data, y_data = sns.distplot(data).get_lines()[0].get_data()
            y_max = y_data.argmax()  # get idx of half maximum
            # get points above/below y_max that is closest to max_y/2 by subtracting it from the data and
            # looking for the minimum absolute value
            nearest_above = (np.abs(y_data[y_max:] - max(y_data) / 2)).argmin()
            nearest_below = (np.abs(y_data[:y_max] - max(y_data) / 2)).argmin()
            # get FWHM by subtracting the x-values of the two points
            fwhm = x_data[nearest_above + y_max] - x_data[nearest_below]
            # return noise level as FWHM/2.3548
            sigma = fwhm/2.3548
            plt.close()
        return sigma

    def align_to_vr_position(self):
        """
        Imports behavioral data (merged_vr_licks.txt) and aligns the traces to it. Then bins the traces to
        achieve a uniform trial length and subsequent place cell analysis.
        Behavioral data is saved in the 'behavior' list that includes one array per trial with the following structure:
            time stamp -> VR position -- time stamp -> lick sensor -- 2p trigger -- time stamp -> encoder (speed)
        Binned data is saved is saved in three formats:
            - as bin_frame_count, an array of shape [n_bins x n_trials] showing the number of frames that have to be
              averaged for each bin in every trial (stored in params)
            - as bin_activity, a list of neurons that consist of an array with shape [n_bins x n_trials] and stores
              the binned dF/F for every trial.
            - as bin_avg_activity, an array of shape [n_neuron x n_bins] that contain the dF/F for each bin of every
              neuron, averaged across trials. This is what will mainly be used for place cell analysis.
        :return: Updated PCF object with behavior and binned trial data
        """
        behavior = []
        if self.params['trial_list'] is not None:
            for trial in self.params['trial_list']:
                behavior.append(np.loadtxt(
                    f'E:\PhD\Data\CA1\Maus 3 13.03.2019 behavior\{trial}\merged_vr_licks.txt'))  # TODO remove hard coding
        else:
            raise Exception('You have to provide trial_list before continuing the analysis!')

        bin_frame_count = np.zeros((self.params['n_bins'], self.params['n_trials']), 'int')
        for trial in range(len(behavior)):  # go through vr data of every trial and prepare it for analysis

            # get a normalized time stamp that is easier to visualize (optional)
            behavior[trial] = np.insert(behavior[trial], 1, behavior[trial][:, 0] - behavior[trial][0, 0], 1)
            # time stamps at data[:,1], position at data[:,2], velocity at data[:,7]

            # bin data in distance chunks
            fr = self.cnmf.params.data['fr']
            bin_borders = np.linspace(-10, 110, self.params['n_bins'] + 1)
            idx = np.digitize(behavior[trial][:, 2], bin_borders)  # get indices of bins

            # create estimate time stamps for frames (only necessary for behavior data without frame trigger)
            last_stamp = 0
            for i in range(behavior[trial].shape[0]):
                if last_stamp + (1 / fr) < behavior[trial][i, 1] or i == 0:
                    behavior[trial][i, 5] = 1
                    last_stamp = behavior[trial][i, 1]

            # check how many frames are in each bin
            for i in range(self.params['n_bins']):
                bin_frame_count[i, trial] = np.sum(behavior[trial][np.where(idx == i + 1), 5])

            # Average dF/F for each neuron for each trial for each bin
            # goes through every trial, extracts frames according to current bin size, averages it and puts it into
            # the data structure "bin_activity", a list of neurons, with every neuron having an array of shape
            # (n_trials X n_bins) containing the average dF/F activity of this bin of that trial
            bin_activity = list(np.zeros(self.params['n_neuron']))
            for neuron in range(self.params['n_neuron']):
                curr_neur_act = np.zeros((self.params['n_trial'], self.params['n_bins']))
                for trial in range(self.params['n_trial']):
                    curr_trace = self.session[neuron][trial]
                    curr_bins = bin_frame_count[:, trial]
                    curr_act_bin = np.zeros(self.params['n_bins'])
                    for bin_no in range(self.params['n_bins']):
                        # extract the trace of the current bin from the trial trace
                        if len(curr_trace) > curr_bins[bin_no]:
                            trace_to_avg, curr_trace = curr_trace[:curr_bins[bin_no]], curr_trace[curr_bins[bin_no]:]
                        elif len(curr_trace) == curr_bins[bin_no]:
                            trace_to_avg = curr_trace
                        else:
                            trace_to_avg = np.nan
                            raise Exception('Something went wrong during binning...')
                        curr_act_bin[bin_no] = np.mean(trace_to_avg)
                    curr_neur_act[trial] = curr_act_bin
                bin_activity[neuron] = curr_neur_act

            # Get average activity across trials of every neuron for every bin
            bin_avg_activity = np.zeros((self.params['n_neuron'], self.params['n_bins']))
            for neuron in range(self.params['n_neuron']):
                bin_avg_activity[neuron] = np.mean(bin_activity[neuron], axis=0)

            self.behavior = behavior
            self.params['bin_frame_count'] = bin_frame_count
            self.bin_activity = bin_activity
            self.bin_avg_activity = bin_avg_activity

            return self

    def find_place_field_trial(self, data, n_neuron):
        """
        Performs place field analysis (smoothing, pre-screening and criteria application) on a single neuron data set.
        :param data: binned and across-trial-averaged dF/F data of one neuron, e.g. from bin_avg_activity
        :param n_neuron: ID of the neuron that the data belongs to
        :return:
        """
        smooth_trace = self.smooth_trace(data)

        # pre-screen for potential place fields
        f_max = max(smooth_trace)  # get maximum DF/F value
        # get baseline dF/F value from the average of the 'bin_base' % least active bins (default 25% of n_bins)
        f_base = np.mean(np.sort(smooth_trace)[:int(smooth_trace.size * self.params['bin_base'])])
        # get threshold value above which a point is considered part of the potential place field (default 25%)
        f_thresh = (f_max - f_base) * self.params['place_thresh']
        # get indices where the smoothed trace is above threshold
        pot_place_idx = np.where(smooth_trace >= f_thresh)[0]
        # split indices into consecutive blocks to get separate place fields
        pot_place_blocks = np.split(pot_place_idx, np.where(np.diff(pot_place_idx) != 1)[0] + 1)

    def smooth_trace(self, trace):
        """
        Smoothes a trace (usually binned, but can also be used unbinned) by averaging each point across adjacent values.
        Sliding window size is determined by params['bin_window_avg'] (default 3).

        :param trace: 1D array containing the data points.
        :return: array of the same size as input trace, but smoothed
        """
        smooth_trace = trace.copy()
        for i in range(len(trace)):
            # get the frame windows around the current time point i
            if i < self.params['bin_window_avg']:
                curr_left_bin = trace[:i]
            else:
                curr_left_bin = trace[i - self.params['bin_window_avg']:i]
            if i + self.params['bin_window_avg'] > len(trace):
                curr_right_bin = trace[i:]
            else:
                curr_right_bin = trace[i:i + self.params['bin_window_avg']]
            curr_bin = np.concatenate((curr_left_bin, curr_right_bin))

            smooth_trace[i] = np.mean(curr_bin)

        return smooth_trace

    def apply_pf_criteria(self, trace, place_blocks):
        """
        Applies the criteria of place fields to potential place fields of a trace. A place field is accepted when...
            1) it stretches at least 'min_bin_size' bins (default 10)
            2) its mean dF/F is larger than outside the field by a factor of 'fluo_infield'
            3) during 'trans_time'% of the time the mouse is located in the field, the signal consists of significant transients
        Place fields that pass these criteria have to have a p-value < 0.05 to be fully accepted. This is checked in
        the bootstrap() function.

        :param place_blocks: list of array(s) that hold bin indices of potential place fields, one array per field (from pot_place_blocks)
        :param trace: 1D array containing the trace in which the potential place fields are located
        :return: list of place field arrays that passed all three criteria.
        """

        for pot_place in place_blocks:
            if self.is_large_enough(pot_place) and self.is_strong_enough(trace, pot_place) and self.has_enough_transients(neuron_id, pot_place):
                # Todo: continue here, implement bootstrapping, implement loop for all cells

    def is_large_enough(self, place_field):
        """
        Checks if the potential place field is large enough according to 'min_bin_size' (criterion 1).
        :param place_field: 1D array of indices of data points that form the potential place field
        :return: boolean value whether the criterion is passed or not
        """
        return place_field.size >= self.params['min_bin_size']

    def is_strong_enough(self, trace, place_field):
        """
        Checks if the place field has a mean dF/F that is 'fluo_infield'x higher than outside the field (criterion 2).
        :param trace: 1D array of the trace data
        :param place_field: 1D array of indices of data points that form the potential place field
        :return: boolean value whether the criterion is passed or not
        """
        pot_place_idx = np.in1d(range(trace.shape[0]), place_field) # get an idx mask for the potential place field
        return np.mean(trace[pot_place_idx]) >= self.params['fluo_infield'] * np.mean(trace[~pot_place_idx])

    def has_enough_transients(self, neuron_id, place_field):
        """
        Checks if of the time during which the mouse is located in the potential field, at least 'trans_time'%
        consist of significant transients (criterion 3).
        :param neuron_id: 1D array of index of the current neuron in the session list
        :param place_field: 1D array of indices of data points that form the potential place field
        :return: boolean value whether the criterion is passed or not
        """
        place_frames_trace = []  # stores the trace of all trials when the mouse was in a place field as one data row
        for trial in range(self.params['bin_frame_count'].shape[1]):
            # get the start and end frame for the current place field from the bin_frame_count array that stores how many
            # frames were pooled for each bin
            curr_place_frames = (np.sum(self.params['bin_frame_count'][:place_field[0], trial]),
                                 np.sum(self.params['bin_frame_count'][:place_field[-1] + 1, trial]))
            # attach the transient-only trace in the place field during this trial to the array
            # TODO: not working with the current behavior data, make it work for behavior&frame-trigger data
            place_frames_trace.append(self.session_trans[neuron_id][trial][curr_place_frames[0]:curr_place_frames[1] + 1])

        # create one big 1D array that includes all frames where the mouse was located in the place field
        # as this is the transient-only trace, we make it boolean, with False = no transient and True = transient
        place_frames_trace = np.hstack(place_frames_trace).astype('bool')
        # check if at least 'trans_time' percent of the frames are part of a significant transient
        return np.sum(place_frames_trace) >= self.params['trans_time'] * place_frames_trace.shape[0]