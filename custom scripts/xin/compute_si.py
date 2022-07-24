#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Created on 18/07/2022 16:58
@author: hheise

Script that computes spatial information and place cell classification.
Requires CaImAn results (cmn_results.hdf5) and VR behavior files.
Based on Shuman 2020 (Nat Neurosci).
"""

import tkinter as tk
from tkinter import filedialog
from typing import Tuple, Any, Union, List
from glob import glob
import os
import numpy as np
from copy import deepcopy

import pandas as pd
from caiman.source_extraction.cnmf import cnmf
from scipy.ndimage import gaussian_filter1d

# USER-CHOSEN PARAMETERS
RUNNING_THR = 5.0  # Number of encoder ticks per frame above which a frame counts as "running"
BIN_LENGTH = 5  # Spatial bin length to pool dF/F traces, in [cm]
SIGMA_GAUSS = 1  # Standard deviation of Gaussian kernel when smoothing spatial activity maps for SI computation
MIN_PF_SIZE = 3  # Minimum number of spatial bins that a place field should have
N_ITER = 1000  # Number of shufflings during bootstrapping. Larger value produces more reliable result, but computation takes longer

n_bins = 400 // BIN_LENGTH  # Track length of 400 cm is assumed

# CASCADE PARAMETERS
MODEL_NAME = 'Global_EXC_30Hz_smoothing50ms'  # Name of the model for deconvolution. The default is good for 30Hz recordings.
THRESHOLD = 0  # Whether deconvoluted trace should be thresholded at the height of 1 spike or not.


def get_session_dir() -> str:
    """
    Open a prompt on top of all other windows which asks the user for the session folder that has to contain the
    cnm_results.hdf5 file and merge_behavior.txt files of all trials of the session to be processed.

    Returns:
        Absolute path of the user-selected directory
    """
    root = tk.Tk()
    root.wm_attributes('-topmost', 1)
    root.withdraw()
    return filedialog.askdirectory(parent=root, title='Choose session directory containing the CNM and merge_behavior '
                                                      'files.')


def load_data(sess_dir: str) -> Tuple[Any, list]:
    """
    Load CNM results file (cnm_results.hdf5) as well as all merged_behavior.txt files for the session.
    The CNM file has to be in sess_dir, the behavior files can be in one subdirectory.

    Args:
        sess_dir: Absolute path of the current session directory containing the files. Output from get_session_dir().

    Returns:
        cnm_obj:            CNMF object containing data from CaImAn pipeline
        behavior_arrays:    list of numpy arrays containing VR behavior data (one list element per trial)
    """
    ### Load CNM file
    cnm_filepath = os.path.join(sess_dir, 'cnm_results.hdf5')
    cnm_file = glob(cnm_filepath)
    if len(cnm_file) < 1:
        raise FileNotFoundError(f'No CNM file found at\n\t{sess_dir}.')
    else:
        print(f'Loading file {cnm_file[0]}...')
        cnm_obj = cnmf.load_CNMF(cnm_file[0])

    ### Load behavior files
    trial_list = glob(
        sess_dir + '\\merged_behavior*.txt')  # Get a list of all merged_behavior.txt files in the session directory and one subdirectory
    trial_list.extend(glob(sess_dir + '\\*\\merged_behavior*.txt'))
    trial_list.sort(key=lambda x: int(x.split('.')[-2].split('_')[-1]))  # Sort trials by their timestamp

    # Load the behavior data as numpy arrays
    if len(trial_list) > 0:
        behavior_arrays = [np.loadtxt(trial, delimiter='\t') for trial in trial_list]
    else:
        raise FileNotFoundError(f'Could not find merged_behavior.txt files at {sess_dir}')
    return cnm_obj, behavior_arrays


def get_trial_mask(cnm_obj, behav_list: list) -> np.ndarray:
    """
    Make arrays of the trial's length with the trial's ID and concatenate them to one mask for the whole session.
    This mask is used to process individual trials in one CNM trace separately.

    Args:
        cnm_obj:    CNM results object. Output from load_data().
        behav_list: List of behavior files. Output from load_data().

    Returns:
        Numpy array with shape (n_frames,) containing trial ID of each frame.
    """
    # Get frame counts of individual trials from behavior data
    frame_counts = [int(np.nansum(behav[:, 3])) for behav in behav_list]

    # Check that all frames are accounted for, otherwise raise error
    if np.sum(frame_counts) != cnm_obj.estimates.F_dff.shape[1]:
        raise IndexError(f'Frame count mismatch:\nFound {np.sum(frame_counts)} frames in merged_behavior.txt files, '
                         f'but CNM file has {cnm_obj.estimates.F_dff.shape[1]} frames.')

    # Make trial mask of each trial
    trial_masks = []
    for idx, n_frame in enumerate(frame_counts):
        trial_masks.append(np.full(n_frame, idx))
    return np.concatenate(trial_masks)


def align_frames_with_vr(behavior_list, tr_mask) -> Tuple[list, list]:
    """
    Synchronize frame times with VR position and count frames for each position bin.
    The result is a 2D array of shape (n_bins, n_trials), which contains the number of frames that have to be averaged
    for each bin in every trial.
    Resting frames, where the mouse is not running, are filtered out with a running mask.

    Args:
        behavior_list:
        tr_mask:

    Returns:
        Running_masks: List with one element per trial, containing for each trial a binary array with shape (n_frames)
            that is False for stationary frames and True for running frames (see threshold).
        bin_frame_count: List with one element per trial, containing frame numbers for each position bin.
    """

    # Make copy of behav_list to not change the original data
    behav_list = deepcopy(behavior_list)

    running_masks = []
    bin_frame_counts = []

    for trial_idx in np.unique(tr_mask):

        # Make mask with length n_frames that is False for frames where the mouse was stationary.
        run_mask = np.ones(len(np.where(tr_mask == trial_idx)[0]), dtype=bool)

        frame_idx = np.where(behav_list[trial_idx][:, 3] == 1)[0]  # find idx of all frames

        # Because data collection starts at the first frame, there is no running data available before it.
        # Mice usually run at the beginning of the trial, so we assume that the frame is not stationary and just
        # skip the first frame and start with i=1.
        for i in range(1, len(frame_idx)):
            if np.mean(behav_list[trial_idx][frame_idx[i - 1]:frame_idx[i], 5]) < RUNNING_THR:
                # set index of mask to False (excluded in later analysis)
                run_mask[i] = False
                # set the bad frame in the behavior array to 0 to skip it during bin_frame_counting
                behav_list[trial_idx][frame_idx[i], 3] = np.nan

        # Get frame counts for each bin for complete trial (moving and resting frames)
        bfc = np.zeros(n_bins, dtype=int)
        # bin data in distance chunks
        bin_borders = np.linspace(-10, 110, n_bins)
        idx = np.digitize(behav_list[trial_idx][:, 1], bin_borders)  # get indices of bins

        # check how many frames are in each bin
        for i in range(n_bins):
            bfc[i] = np.nansum(behav_list[trial_idx][np.where(idx == i + 1), 3])

        # check that every bin has at least one frame in it
        if np.any(bfc == 0):
            all_zero_idx = np.where(bfc == 0)[0]
            # if not, take a frame of the next bin. If the mouse is running that fast, the recorded calcium will lag
            # behind the actual activity in terms of mouse position, so spikes from a later time point will probably be
            # related to an earlier actual position. (or the previous bin in case its the last bin)
            for zero_idx in all_zero_idx:
                # If the bin with no frames is the last bin, take one frame from the second-last bin
                if zero_idx == n_bins - 1 and bfc[-2] > 1:
                    bfc[-2] -= 1
                    bfc[-1] += 1
                # Otherwise, take it from the next bin, but only if the next bin has more than 1 frame itself
                elif zero_idx < n_bins - 1 and bfc[zero_idx + 1] > 1:
                    bfc[zero_idx + 1] -= 1
                    bfc[zero_idx] += 1
                # This error is raised if two consecutive bins have no frames
                else:
                    raise ValueError('Error:\nNo frames found for bin {}, could not be corrected.'.format(zero_idx))

        if not np.sum(bfc) == np.sum(run_mask):
            raise ValueError('Error in trial {}:\nBinning failed, found {} running frames, but {} frames in '
                             'bin_frame_count'.format(trial_idx, np.sum(run_mask), np.sum(bfc)))

        # Append the running mask and bin_frame_count of the current trial
        running_masks.append(run_mask)
        bin_frame_counts.append(bfc)

    return running_masks, bin_frame_counts


def run_cascade(dff: np.ndarray) -> np.ndarray:
    """
    Wrapper function to run Peter's CASCADE deconvolution algorithm (see https://github.com/HelmchenLabSoftware/Cascade).

    Args:
        dff: dF/F activity traces of all neurons, with shape (n_cells, n_frames)

    Returns:
        2D np.ndarray with same shape as input, containing deconvolved spike probability per frame.
    """

    from cascade2p import checks, cascade
    # To run deconvolution, tensorflow, keras and ruaml.yaml must be installed
    checks.check_packages()

    print('Using deconvolution model {}'.format(MODEL_NAME))

    # model is saved in subdirectory models of cascade2p
    import inspect
    cascade_path = os.path.dirname(inspect.getfile(cascade))
    model_folder = os.path.join(cascade_path, 'Pretrained_models')

    # Transform traces back to float64 to not confuse CASCADE
    decon_traces, trace_noise_levels = cascade.predict(MODEL_NAME, np.array(dff, dtype=np.float64),
                                                       model_folder=model_folder, threshold=THRESHOLD, padding=0)
    # Store traces in float32 to save disk space
    return np.array(decon_traces, dtype=np.float32)


def bin_activity_to_vr(spikes: np.ndarray, tr_mask: np.ndarray, running_masks: list,
                       bin_frame_counts: Union[np.ndarray, list], fr) -> np.ndarray:
    """
    Spatially bins the dF/F and deconvolved traces of many neurons to the VR position. Extracted from
    BinnedActivity.make() because it is also used to bin the shuffled trace during place cell bootstrapping.

    Args:
        spikes: CASCADE spike prediction of the trace, with shape (n_neurons, n_frames_in_session).
        tr_mask: 1D array with length n_frames_in_session, from get_trial_mask().
        running_masks: One element per trial, from align_frames_with_vr().
        bin_frame_counts: Same as running_masks, from align_frames_with_vr().
        fr: frame rate of the recording, in Hz

    Returns:
        3D np.darray with shape (n_neurons, n_bins, n_trials), spatially binned spikerate.
    """

    n_trials = len(running_masks)

    binned_spike = np.zeros((spikes.shape[0], n_bins, n_trials))
    binned_spikerate = np.zeros((spikes.shape[0], n_bins, n_trials))

    for trial_idx, (run_mask, bin_frame_count) in enumerate(zip(running_masks, bin_frame_counts)):
        # Create bin mask from frame counts
        bin_masks = []
        for idx, n_frames in enumerate(bin_frame_count):
            bin_masks.append(np.full(n_frames, idx))
        bin_mask = np.concatenate(bin_masks)

        # Get section of current trial from the session-wide trace and filter out non-running frames
        trial_spike = spikes[:, tr_mask == trial_idx][:, run_mask]

        # Iteratively for all bins, average trace and sum spike probabilities
        for bin_idx in range(n_bins):
            bin_spike = trial_spike[:, bin_mask == bin_idx]

            if bin_spike.shape[1]:  # Test if there is data for the current bin, otherwise raise error
                # sum spike values (CASCADE's spike probability is cumulative)
                binned_spike[:, bin_idx, trial_idx] = np.nansum(bin_spike, axis=1)
            else:
                raise IndexError("Bin {} returned empty array, could not bin trace.".format(bin_idx))

        # Transform deconvolved values into mean firing rates by dividing by the time in s occupied by the bin (from
        # number of samples * sampling rate)
        bin_times = bin_frame_count / fr
        binned_spikerate[:, :, trial_idx] = binned_spike[:, :, trial_idx] / bin_times

    return binned_spikerate


def spatial_info(traces: np.ndarray, bin_frame_count: List[np.ndarray], deconv: np.ndarray, tr_mask: np.ndarray,
                 run_masks: List[np.ndarray], frame_rate: float) -> pd.DataFrame:
    """
    Place cell classification using spatial information in deconvolved spikerates. Adapted from Shuman (2020).

    Args:
        traces: Array with shape (n_neurons, n_bins), containing spatial activity maps of all neurons. From bin_activity_to_vr().
        bin_frame_count: Frame numbers per position bin for all trials. From align_frames_with_vr().
        deconv: Unbinned spikerates with shape (n_neurons, n_frames). From run_cascade().
        tr_mask: 1D array with length n_frames_in_session, from get_trial_mask().
        run_masks: List of binary masks showing running (True) and resting (False) frames, from align_frames_with_vr().
        frame_rate: Frame rate of the recording, from cnm object.

    Returns:
        Pandas DataFrame with all results from the spatial information analysis. Columns contain different
        metrics/results, each row has data from a single cell. The metrics/columns are:
        - cell_id: Integer index of each cell/row
        - si: Spatial information content, in bits/spike
        - p_si: Percentages of shuffled traces that had a higher SI value than the real trace. Can be interpreted as p-value.
        - stability: Within-session stability, measured via cross-correlation.
        - p_stability: Same as p_si, but for stability value
        - place_fields: List of position bins part of place field(s) of this cell. (MIN_PF_SIZE consecutive bins with
            activity higher than 95th percentile of shuffled traces)
        - pf_threshold: 95th percentile threshold used as a place field criterion
        - is_pc: Bool flag whether a cell passes all 3 criteria (p-values of SI and stability < 0.05, and has place fields)
    """

    def compute_spatial_info(act_map: np.ndarray, occupancy: List[np.ndarray], sigma: int) -> np.ndarray:
        """
        Computes spatial information per spike for all cells. Original formula is from Skaggs (1992) mutual information
        and adapted to calcium imaging data by Shuman (2020).

        Args:
            act_map: Spatially binned spikerates with shape (n_cells, n_bins, n_trials).
            occupancy: Frame numbers per position bin for all trials.
            sigma: Standard deviation of Gaussian kernel for binned spikerate smoothing.

        Returns:
            Numpy array with shape (n_cells) with the spatial information values per cell.
        """
        p_occ = np.sum(occupancy, axis=0) / np.sum(occupancy)  # Occupancy probability per bin p(i)
        p_occ = p_occ[None, :]
        act_bin = np.mean(gaussian_filter1d(act_map, sigma, axis=1), axis=2)  # Smoothed activity rate per bin lambda(i)
        # Normalize SI by activity level (lambda-bar) to make SI value more comparable between cells
        act_rel = act_bin.T / np.sum(p_occ * act_bin, axis=1)
        return np.sum(p_occ * act_rel.T * np.log2(act_rel.T), axis=1)

    def compute_within_session_stability(act_map: np.ndarray, sigma: int) -> np.ndarray:
        """
        Computes within-session stability of spikerates across trials after Shuman (2020). Trials are averaged and
        correlated across two timescales: First vs. second half of the session and even vs. odd trials. The Pearson
        correlation coefficients are Fisher z-scored to make them comparable, and their average is the stability
        value of the cell.

        Args:
            act_map: Spatially binned spikerates with shape (n_cells, n_bins, n_trials).
            sigma: Standard deviation of Gaussian kernel for binned spikerate smoothing.

        Returns:
            Numpy array with shape (n_cells) with stability value of each cell.
        """
        smoothed = gaussian_filter1d(act_map, sigma, axis=1)
        # First, correlate trials in the first vs second half of the session
        half_point = int(np.round(smoothed.shape[2] / 2))
        first_half = np.mean(smoothed[:, :, :half_point], axis=2)
        second_half = np.mean(smoothed[:, :, half_point:], axis=2)
        r_half = np.vstack([np.corrcoef(first_half[x], second_half[x])[0, 1] for x in range(len(smoothed))])
        fisher_z_half = np.arctanh(r_half)

        # Then, correlate even and odd trials
        even = np.mean(smoothed[:, :, ::2], axis=2)
        odd = np.mean(smoothed[:, :, 1::2], axis=2)
        r_even = np.vstack([np.corrcoef(even[x], odd[x])[0, 1] for x in range(len(smoothed))])
        fisher_z_even = np.arctanh(r_even)

        # Within-session stability is the average of the two measures
        stab = np.mean(np.hstack((fisher_z_half, fisher_z_even)), axis=1)

        return stab

    def circular_shuffle(data: np.ndarray, t_mask: np.ndarray, r_mask: List[np.ndarray], occupancy: List[np.ndarray],
                         num_bins: int, n_iter: int, fr: float) -> np.ndarray:
        """
        Performs circular shuffling of activity data to creating surrogate data for significance testing (after
        Shuman 2020). Each trial is circularly shifted by +/- trial length. Traces from adjacent trials shifts in
        and out of view at the ends. For the first and last trial, the trial trace is shifted inside itself.
        The shifted data is binned with the original occupancy data, so that each frame now is associated with a
        different position.

        Args:
            data: Unbinned deconvolved spikerate with shape (n_cells, n_frames). From run_cascade().
            t_mask: Trial mask with shape (n_frames) with accepted trial identity for every frame.
            r_mask: Boolean running mask with shape (n_frames) with True for frames where the mouse was running.
            occupancy:  Frame counts of spatial bins with shape (n_trials, n_bins).
            num_bins: Number of spatial bins in which the signal should be binned.
            n_iter: Number of iterations of shuffling.
            fr: Frame rate of the recording.

        Returns:
            Np.array with shape (n_iter, n_cells, num_bins, n_trials) with the shuffled activity data.
        """

        # Shuffled traces are stored in this array with shape (n_iter, n_rois, n_bins, n_trials)
        shuffle_data = np.zeros((n_iter, len(data), num_bins, len(r_mask))) * np.nan

        for shuff in range(n_iter):
            shift = []  # The shifted traces for the current shuffle
            bin_f_counts = []  # Holds bin frame counts for accepted trials
            trial_mask_accepted = []  # Holds trial mask for accepted trials
            dummy_running_masks = []  # Dummy mask that allows all frames (needed for bin_activity_to_vr())

            for rel_idx, trial_id in enumerate(np.unique(t_mask)):
                # Get trace from the current trial and remove resting frames
                curr_trace = data[:, t_mask == trial_id][:, r_mask[rel_idx]]

                # Possible shifts are +/- half of the trial length (Aleksejs suggestion)
                d = np.random.randint(-data.shape[1] // 2, data.shape[1] // 2 + 1)

                dummy_running_masks.append(np.ones(curr_trace.shape[1], dtype=bool))

                # Circularly shift traces
                if trial_id == np.unique(t_mask)[0] or trial_id == np.unique(t_mask)[-1]:
                    # The first and last trials have to be treated differently: traces are circulated in-trial
                    shift.append(np.roll(curr_trace, d, axis=1))
                else:
                    # For all other trials, we shift them together with the previous and next trial
                    prev_trial = data[:, t_mask == trial_id - 1]
                    next_trial = data[:, t_mask == trial_id + 1]
                    # Make the previous, current and next trials into one array
                    neighbor_trials = np.hstack((prev_trial, curr_trace, next_trial))
                    # Roll that array and take the values at the indices of the current trial
                    shift.append(np.roll(neighbor_trials, d, axis=1)[:, prev_trial.shape[1]:-next_trial.shape[1]])

                # Add entries of bin_frame_counts and trial_mask for accepted trials
                bin_f_counts.append(occupancy[rel_idx])
                trial_mask_accepted.append(np.array([rel_idx] * curr_trace.shape[1], dtype=int))

            # The binning function requires the whole session in one row, so we stack the single-trial-arrays
            shift = np.hstack(shift)
            trial_mask_accepted = np.hstack(trial_mask_accepted)

            bin_shift = bin_activity_to_vr(shift, trial_mask_accepted, dummy_running_masks, bin_f_counts, fr)
            shuffle_data[shuff] = bin_shift

        return shuffle_data

    n_bin = len(bin_frame_count[0])

    ### SPATIAL INFORMATION ###
    # Compute SI of real data
    print('\tComputing spatial information...(1/3)')
    real_si = compute_spatial_info(traces, bin_frame_count, SIGMA_GAUSS)

    # Perform circular shuffling and get SI of shuffled data
    shuffled_data = circular_shuffle(data=deconv, t_mask=tr_mask, r_mask=run_masks, occupancy=bin_frame_count,
                                     num_bins=n_bin, n_iter=N_ITER, fr=frame_rate)
    shuffles = np.zeros((shuffled_data.shape[0], shuffled_data.shape[1])) * np.nan
    for i, shuffle in enumerate(shuffled_data):
        shuffles[i] = compute_spatial_info(shuffle, bin_frame_count, SIGMA_GAUSS)

    # Find percentile -> SI of how many shuffles were higher than the real SI
    si_percs = np.sum(shuffles > real_si[None, :], axis=0) / N_ITER

    ### WITHIN-SESSION STABILITY ###
    # Compute stability of real data
    print('\tComputing within-session stability...(2/3)')
    real_stab = compute_within_session_stability(act_map=traces, sigma=SIGMA_GAUSS)

    # Perform circular shuffling and get stability of shuffled data
    shuffled_data = circular_shuffle(data=deconv, t_mask=tr_mask, r_mask=run_masks, occupancy=bin_frame_count,
                                     num_bins=n_bin, n_iter=N_ITER, fr=frame_rate)
    shuffle_stab = np.zeros((shuffled_data.shape[0], shuffled_data.shape[1])) * np.nan
    for i, shuffle in enumerate(shuffled_data):
        shuffle_stab[i] = compute_within_session_stability(shuffle, SIGMA_GAUSS)

    # Find percentile -> stability of how many shuffles were higher than the real stability
    stab_perc = np.sum(shuffle_stab > real_stab[None, :], axis=0) / N_ITER

    ### PLACE FIELD ACTIVITY ###
    # Create shuffled dataset again
    print('\tCheck for significant place fields...(3/3)')
    shuffled_data = circular_shuffle(data=deconv, t_mask=tr_mask, r_mask=run_masks, occupancy=bin_frame_count,
                                     num_bins=n_bin, n_iter=N_ITER, fr=frame_rate)
    # Average data across trials
    shuffled_data = np.mean(shuffled_data, axis=3)
    # Get 95th percentile for each neuron's binned activity across shuffles
    perc95 = np.percentile(shuffled_data, 95, axis=(0, 2))
    # Find bins with higher activity than perc95
    above_95 = np.mean(traces, axis=2) >= perc95[:, None]
    active_bin_coords = np.where(above_95)

    # Check for consecutive bins of at least "min_bin_size" size
    large_fields = [[] for i in range(len(traces))]
    for cell in np.unique(active_bin_coords[0]):
        curr_bin_idx = active_bin_coords[1][active_bin_coords[0] == cell]
        curr_bin_list = np.split(curr_bin_idx, np.where(np.diff(curr_bin_idx) != 1)[0] + 1)
        large_fields[cell] = [x for x in curr_bin_list if len(x) >= MIN_PF_SIZE]

    # Apply place cell criteria
    spat_inf = [perc < 0.05 for perc in si_percs]
    stability = stab_perc < 0.05
    place_fields = [len(x) > 0 for x in large_fields]
    criteria = np.vstack((spat_inf, stability, place_fields))
    place_cell = (np.sum(criteria, axis=0) == 3).astype(int)

    # Collect data and put it together in a DataFrame
    return pd.DataFrame(dict(cell_id=np.arange(len(traces)), si=real_si, p_si=si_percs, stability=real_stab,
                             p_stability=stab_perc, place_fields=large_fields, pf_threshold=perc95,
                             is_pc=place_cell))


def run_pipeline() -> None:
    """
    Main function that runs all functions for the spatial information pipeline in order. This function can be called
    by other code to incorporate the script into an existing pipeline.
    """

    # Ask user for location of session to be processed
    session_dir = get_session_dir()
    print(f'Starting analysis on {session_dir}...')

    # Load cnm and behavioral data
    cnm, behavior = load_data(session_dir)

    # Split traces into trials
    trial_mask = get_trial_mask(cnm, behavior)

    # Filter out stationary frames and align imaging frames with VR position
    running_mask, bf_count = align_frames_with_vr(behavior, trial_mask)

    # Perform deconvolution with Peter's CASCADE on the dF/F traces from CaImAn
    decon = run_cascade(cnm.estimates.F_dff)

    # Bin traces to VR position
    bin_spikes = bin_activity_to_vr(decon, trial_mask, running_mask, bf_count, cnm.params.data['fr'])

    # Compute spatial information content and classify place cells
    print('Running spatial information algorithm...')
    data = spatial_info(traces=bin_spikes, bin_frame_count=bf_count, deconv=decon, tr_mask=trial_mask,
                        run_masks=running_mask, frame_rate=cnm.params.data['fr'])

    # Save data in the session directory
    print('Saving files...')
    np.save(os.path.join(session_dir, 'decon.npy'), decon, allow_pickle=False)
    np.save(os.path.join(session_dir, 'spatial_info.npy'), data.to_numpy(), allow_pickle=False)

    print('Done!')


if __name__ == '__main__':
    # If the script is run from the command line, run the whole pipeline
    run_pipeline()