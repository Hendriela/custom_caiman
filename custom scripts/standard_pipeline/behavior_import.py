import numpy as np
from glob import glob
from math import ceil, floor
import sys
import os
from timeit import default_timer as timer
from ScanImageTiffReader import ScanImageTiffReader
from datetime import datetime, timedelta
from standard_pipeline import performance_check as performance
from pathlib import Path
import pandas as pd


def load_file(path):
    """
    Loads Files from a directory, with error messages in case there is none or more than 1 file with that name.
    :param path: directory
    :return: loaded file as np.array
    """
    file_path = glob(path)
    if len(file_path) < 1:
        raise Exception(f'No files found at {path}!')
    elif len(file_path) > 1:
        raise Exception(f'File name ambiguous, multiple files found at {path}')
    else:
        return np.loadtxt(file_path[0])


def progress(count, total, status='', percent=True):
    """
    Displays an automatically updating progress bar in the console, showing progress of a for-loop.
    :param count: int, current iteration of the loop (current progress)
    :param total: int, maximum iteration of the loop (end point)
    :param status: str, status message displayed next to the progress bar
    :param percent: bool, flag whether progress should be displayed as percentage or absolute fraction
    :return:
    """
    bar_len = 20
    filled_len = int(round(bar_len * count / float(total)))
    percents = round(100.0 * count / float(total), 1)
    bar = '=' * filled_len + '-' * (bar_len - filled_len)
    if percent:
        sys.stdout.write('[%s] %s%s ...%s\r' % (bar, percents, '%', status))
    else:
        sys.stdout.write('[%s] %s%s ...%s\r' % (bar, count, f'/{total}', status))
    sys.stdout.flush()


def align_behavior(root, performance_check=True, overwrite=False, verbose=False, enc_unit='speed', skip_sessions=None):
    """
    This function is the main function called by pipelines!
    Wrapper for aligning multiple behavioral files. Looks through all subfolders of root for behavioral files.
    If it finds a folder with behavioral files but without merged_behavior.txt, it aligns them.
    If the folder does not contain a .tif file (training without imaging), frame trigger is ignored.
    Calls either align_nonfolder_files in case of training data or align_folder_files for combined imaging data
    :param root:                string, path of the folder where files are searched
    :param performance_check:   boolean flag whether performance should be checked during alignment
    :param overwrite:           bool flag whether trials that have been already processed should be aligned again
                                (useful if the alignment script changed and data has to be re-aligned)
    :param verbose:             bool flag whether unnecessary status updates should be printed to the console
    :param enc_unit:            str, if 'speed', encoder data is translated into cm/s; otherwise raw encoder data in
                                rotation [degrees] / sample window (8 ms) is saved
    :param skip_sessions:       optional, str path to .txt file where processed sessions are saved and sessions in this
                                file are skipped. Useful when the whole dataset should be processed once in batches.
    :return:                    saves merged_behavior.txt for each aligned trial
    """
    # list that includes session that have been processed to avoid processing a session multiple times
    processed_sessions = []
    for step in os.walk(root):
        if len(step[2]) > 0:   # check if there are files in the current folder
            if len(glob(step[0] + r'\\Encoder*.txt')) > 0:  # check if the folder has behavioral files
                if len(glob(step[0] + r'\\merged*.txt')) == 0 or overwrite:
                    # If necessary, read the sessions that should be skipped from the provided file
                    if skip_sessions is not None:
                        with open(skip_sessions, 'r') as skip_file:
                            sess_to_skip = skip_file.read().splitlines()
                    # If the log file is in the same folder as the behavioral files, its a non-imaging session
                    if len(glob(step[0] + r'\\TDT LOG*.txt')) > 0:
                        sess_folder = step[0]
                        if sess_folder not in processed_sessions:        # check if session folder has been processed
                            if (skip_sessions is not None and sess_folder not in sess_to_skip) or skip_sessions is None:
                                align_files(sess_folder, imaging=False, verbose=verbose, enc_unit=enc_unit)
                    # If the LOG file is in the parent directory, its an imaging session
                    elif len(glob(str(Path(step[0]).parents[0]) + r'\\TDT LOG*.txt')) > 0:
                        sess_folder = str(Path(step[0]).parents[0])
                        if sess_folder not in processed_sessions:
                            if (skip_sessions is not None and sess_folder not in sess_to_skip) or skip_sessions is None:
                                align_files(sess_folder, imaging=True, verbose=verbose, enc_unit=enc_unit)
                    # If there is no LOG file (first Batch2 sessions), assume that its a non-imaging session
                    else:
                        sess_folder = step[0]
                        if sess_folder not in processed_sessions:
                            if skip_sessions and sess_folder not in sess_to_skip:
                                align_files(sess_folder, imaging=False, verbose=verbose, enc_unit=enc_unit)

                    # calculate licking and stopping performance
                    if skip_sessions is not None:
                        if performance_check and sess_folder not in sess_to_skip:
                            if verbose:
                                print(f'Saving performance for {sess_folder}')
                            performance.save_performance_data(sess_folder)
                    else:
                        if performance_check and sess_folder not in processed_sessions:
                            if verbose:
                                print(f'Saving performance for {sess_folder}')
                            performance.save_performance_data(sess_folder)
                    processed_sessions.append(sess_folder)

                    # Write the session folder in the file to avoid processing it again
                    if skip_sessions is not None and sess_folder not in sess_to_skip:
                        with open(skip_sessions, 'a') as skip_file:
                            out = skip_file.write(f'{sess_folder}\n')

                else:
                    if verbose:
                        print(f'\nSession {step[0]} already processed.')
            else:
                if verbose:
                    print(f'No behavioral files in {step[0]}.')
    print('\nEverything processed!')


def align_files(root, imaging, verbose=False, enc_unit='speed'):
    """
    Wrapper for that calls align_behavior_files for the proper files. Works for both imaging and non-imaging structure.
    This function is called separately for one session.
    :param root:            str, path to the session folder (includes behavioral .txt files)
    :param imaging:         boolean flag whether this was an imaging trial (.tif files exist)
    :param verbose:         boolean flag whether unnecessary status updates should be printed to the console
    :param enc_unit:        str, if 'speed', encoder data is translated into cm/s; otherwise raw encoder data in
                            rotation [degrees] / sample window (8 ms) is saved
    :return: saves merged_behavior_timestamp.txt for each aligned trial
    """
    def find_file(tstamp, file_list):
        """
        Finds a file with the same timestamp from a list of files.
        """
        time_format = '%H%M%S'
        time_stamp = datetime.strptime(tstamp, time_format)
        matched_file = []
        for filename in file_list:
            curr_stamp = datetime.strptime(filename.split('_')[-1][:-4], time_format)
            diff = time_stamp-curr_stamp
            if abs(diff.total_seconds()) < 3:
                matched_file.append(filename)
        if len(matched_file) == 0:
            print(f'No files with timestamp {tstamp} found in {root}!')
            return
        elif len(matched_file) > 1:
            print(f'More than one file with timestamp {tstamp} found in {root}!')
            return
        else:
            return matched_file[0]

    print(f'\nStart processing session {root}...')
    if imaging:
        enc_files = glob(root + r'\\**\\Encoder*.txt')
        pos_files = glob(root + r'\\**\\TCP*.txt')
        trig_files = glob(root + r'\\**\\TDT TASK*.txt')

    else:
        enc_files = glob(root + r'\\Encoder*.txt')
        pos_files = glob(root + r'\\TCP*.txt')
        trig_files = glob(root + r'\\TDT TASK*.txt')

    if not len(enc_files) == len(pos_files) & len(enc_files) == len(trig_files):
        print(f'Uneven numbers of encoder, position and trigger files in folder {root}!')
        return

    counter = 1

    for file in enc_files:
        timestamp = os.path.basename(file).split('_')[1][:-4]
        pos_file = find_file(timestamp, pos_files)
        trig_file = find_file(timestamp, trig_files)
        if pos_file is None or trig_file is None:
            return
        if verbose:
            print(f'\nNow processing trial {counter} of {len(enc_files)}, time stamp {timestamp}...')
        frame_count = None
        if imaging:
            old_file = glob(os.path.dirname(file) + r'\\merged_behavior*.txt')
            if len(old_file) == 1:
                # use the sum of frame triggers from previous merged behavior file (loads faster than raw movie)
                frame_count = int(np.sum(np.loadtxt(old_file[0])[:, 3]))
            else:
                # if trial has not been aligned yet, get frame count from raw file (either one has to be present)
                movie_path = glob(str(Path(file).parents[0]) + r'\\*.tif')
                if len(movie_path) == 1:
                    with ScanImageTiffReader(movie_path[0]) as tif:
                        frame_count = tif.shape()[0]
                elif len(movie_path) > 1:
                    print(f'More than one TIFF file at {root}! Skipping trial, please check!')
                    continue
                else:
                    print(f'No TIFF files or previous merged_behavior files at {root}! Skipping trial, please check!')
                    continue

        # Get path of LOG file
        log_files = glob(root + r'\\TDT LOG*.txt')
        if len(log_files) == 1:
            log_file = log_files[0]
        elif len(log_files) > 1:
            print(f'More than one LOG file in {root}. Try to merge them before processing!')
            log_file = None
        else:
            log_file = None

        merge = align_behavior_files(file, pos_file, trig_file, log_file, imaging=imaging,
                                                frame_count=frame_count, verbose=verbose, enc_unit=enc_unit)

        if merge is not None:
            # save file (4 decimal places for time (0.5 ms), 2 dec for position, ints for lick, trigger, encoder)
            if imaging:
                file_path = os.path.join(str(Path(file).parents[0]), f'merged_behavior_{timestamp}.txt')
            else:
                file_path = os.path.join(root, f'merged_behavior_{timestamp}.txt')
            np.savetxt(file_path, merge, delimiter='\t',
                       fmt=['%.5f', '%.3f', '%1i', '%1i', '%1i', '%.2f', '%1i'],
                       header='Time\tVR pos\tlicks\tframe\tencoder\tcm/s\treward')
            if verbose:
                print(f'Done! \nSaving merged file to {file_path}...\n')

        else:
            print(f'Skipped trial {file}, please check!')

        counter += 1
    print('Done!\n')


def align_behavior_files_old(enc_path, pos_path, trig_path, imaging=False, frame_count=None, enc_unit='speed', verbose=False):
    """
    Main function that aligns behavioral data from three text files to a common master time frame provided by LabView.
    Data are re-sampled at the rate of the data type with the highest sampling rate (TDT, 2 kHz). Missing values of data
    with lower sampling rate are filled in based on their last available value.
    :param enc_path: str, path to the Encoder.txt file (running speed)
    :param pos_path: str, path to the TCP.txt file (VR position)
    :param trig_path: str, path to the TDT.txt file (licking and frame trigger)
    :param imaging: bool flag whether the behavioral data is accompanied by an imaging movie
    :param frame_count: int, frame count of the imaging movie (if imaging=True)
    :param enc_unit: str, if 'speed', encoder data is translated into cm/s; otherwise raw encoder data in
                     rotation [degrees] / sample window (8 ms) is saved
    :param verbose: bool flag whether status updates should be printed into the console (progress bar not affected)
    :return: merge, np.array with columns [time stamp - position - licks - frame - encoder]
    """
    # Load behavioral files
    encoder = load_file(enc_path)
    position = load_file(pos_path)
    trigger = load_file(trig_path)
    raw_trig = trigger.copy()

    if imaging and frame_count is None:
        print(f'Error in trial {enc_path}: provide frame count if imaging=True!')
        return None, None

    # check if the trial might be incomplete (VR not run until the end or TDT file incomplete)
    if max(position[:, 1]) < 110 or abs(position[-1, 0] - trigger[-1, 0]) > 2:
        print('Trial incomplete, please remove file!')
        with open(r'W:\Neurophysiology-Storage1\Wahl\Hendrik\PhD\Data\Batch2\bad_trials.txt', 'a') as bad_file:
            out = bad_file.write(f'{trig_path}\n')
        return None, None

    ### check if a file was copied from the previous one (bug in LabView), if the start time stamp differs by >2s
    # transform the integer time stamps into datetime objects
    time_format = '%H%M%S%f'
    enc_time = datetime.strptime(str(int(encoder[0, 0])), time_format)
    pos_time = datetime.strptime(str(int(position[0, 0])), time_format)
    trig_time = datetime.strptime(str(int(trigger[0, 0])), time_format)
    # calculate absolute difference in seconds between the start times
    diff = (abs((enc_time - pos_time).total_seconds()),
            abs((enc_time - trig_time).total_seconds()),
            abs((trig_time - pos_time).total_seconds()))
    if max(diff) > 2:
        print(f'Faulty trial (TDT file copied from previous trial), time stamps differed by {int(max(diff))}s!')
        with open(r'W:\Neurophysiology-Storage1\Wahl\Hendrik\PhD\Data\Batch2\bad_trials.txt', 'a') as bad_file:
            out = bad_file.write(f'{trig_path}\tTDT from previous trial, diff {int(max(diff))}s\n')
        return None, None

    # determine the earliest time stamp in the logs as a starting point for the master time line
    earliest_time = min(enc_time, pos_time, trig_time)
    # get the offsets of every file in milliseconds
    offsets = ((enc_time - earliest_time),
               (pos_time - earliest_time),
               (trig_time - earliest_time))
    offsets = [time.microseconds/1000000 for time in offsets]
    # apply offsets to the data so that millisecond-time stamps are aligned, and remove artifact data points
    encoder[:, 0] = encoder[:, 0] + offsets[0]  # apply offset
    encoder[:, 0] = [ceil(x * 1000) / 1000 for x in encoder[:, 0]]  # round up time stamp to ms scale
    encoder = np.delete(encoder, 0, 0)  # remove first row (master timestamp, unnecessary for further processing)

    position[:, 0] = position[:, 0] + offsets[1]
    position[:, 0] = [ceil(x * 1000) / 1000 for x in position[:, 0]]
    pos_to_be_del = np.append([0, 1], np.arange(np.argmax(position[:, 1])+1, position.shape[0]))
    position = np.delete(position, pos_to_be_del, 0)   # remove all data points after maximum position (end of corridor)
    position[position[:, 1] < -10, 1] = -10    # cap position values to -10 and 110
    position[position[:, 1] > 110, 1] = 110

    trigger[:, 0] = trigger[:, 0] + offsets[2]
    trigger[:, 0] = [ceil(x * 100000) / 100000 for x in trigger[:, 0]]
    trigger = np.delete(trigger, 0, 0)
    raw_trig = np.delete(raw_trig, 0, 0)

    if imaging:
        ### process frame trigger signal
        frames_to_prepend = 0
        # get a list of indices for every time stamp a frame was acquired
        trig_blocks = np.split(np.where(trigger[:, 2])[0], np.where(np.diff(np.where(trigger[:, 2])[0]) != 1)[0] + 1)
        # take the middle of each frame acquisition as the unique time stamp of that frame, save trigger idx in a list
        trig_idx = []
        for block in trig_blocks:
            trigger[block, 2] = 0  # set the whole period to 0
            if np.isnan(np.mean(block)):
                print(f'No frame trigger in {trig_path}. Check file!')
                return None, None
            trigger[int(round(np.mean(block))), 2] = 1
            trig_idx.append(int(round(np.mean(block))))

        # check if imported frame trigger matches frame count of .tif file and try to fix it
        more_frames_in_TDT = int(np.sum(trigger[:, 2]) - frame_count)  #positive if TDT, negative if .tif had more frames
        if more_frames_in_TDT == 0 and verbose:
            print('Frame count matched, no correction necessary.')
        elif more_frames_in_TDT <= -1:
            # first check if TDT has been logging shorter than TCP
            tdt_offset = position[-1, 0] - trigger[-1, 0]
            # if all missing frames would fit in the offset (time where tdt was not logging), add the frames in the end
            if tdt_offset/0.033 > abs(more_frames_in_TDT):
                print('TDT not logging long enough, too long trial?')
                #trigger = append_frames(trigger, tdt_offset, more_frames_in_TDT)
            # if TDT file had too little frames, they are assumed to have been recorded before TDT logging
            # these frames are added after merge array has been filled
            frames_to_prepend = abs(more_frames_in_TDT)

        elif more_frames_in_TDT > 0:
            # if TDT included too many frames, its assumed that the false-positive frames are from the end of recording
            if more_frames_in_TDT < 5:
                for i in range(more_frames_in_TDT):
                    trigger[trig_blocks[-i], 2] = 0
            else:
                print(f'{more_frames_in_TDT} too many frames imported from TDT, could not be corrected!')
                with open(r'W:\Neurophysiology-Storage1\Wahl\Hendrik\PhD\Data\Batch2\bad_trials.txt', 'a') as bad_file:
                    out = bad_file.write(f'{trig_path}\n')
                return None, None

    ### create the master time line, with one sample every 0.5 milliseconds
    # get maximum and minimum time stamps, rounded to the nearest 0.5 ms step
    min_time = (5 * floor(min(encoder[0, 0], position[0, 0], trigger[0, 0]) / 0.0005)) / 10000
    max_time = (5 * ceil(max(encoder[-1, 0], position[-1, 0], trigger[-1, 0]) / 0.0005)) / 10000
    master_time = np.arange(start=round(min_time * 10000), stop=round((max_time + 0.0005) * 10000),
                            step=5, dtype=int) / 10000
    # create master array with columns [time stamp - position - licks - frame - encoder]
    merge = np.array((master_time, np.zeros(master_time.shape[0]), np.zeros(master_time.shape[0]),
                      np.zeros(master_time.shape[0]), np.zeros(master_time.shape[0]))).T
    for i in [1, 2, 3, 4]:
        merge[:, i] = np.nan

    # go through data and order it into the correct time bin by looking for the time stamp of merge in the other arrays
    # if precise time stamp does not have data, fill in the value of the most recent available time
    start = timer()
    for i in range(merge.shape[0] - 1):
        # first initialization of sliding range windows that avoid repetitive indexing
        if i == 0:
            old_pos = 3
            new_pos = 3
            last_pos = -10
            curr_pos_range = position[new_pos - 3:new_pos + 3, :].copy()
            old_enc = 3
            new_enc = 3
            last_enc = 0
            curr_enc_range = encoder[new_enc - 3:new_enc + 3, :].copy()
            old_trig = 3
            new_trig = 3
            last_lick = 0
            curr_trig_range = trigger[new_trig - 3:new_trig + 3, :].copy()
        curr_merge = merge[[i, i+1]].copy()     # save the current merge 0.5 ms window to avoid repetitive indexing

        #### look for correct position time step ###
        # if position window has to be updated, re-select the current range of position values
        if new_pos != old_pos:
            if new_pos+3 < position.shape[0]:
                curr_pos_range = position[new_pos-3:new_pos+3, :].copy()
            else:
                curr_pos_range = position[new_pos-3:, :].copy()
        old_pos = new_pos        # update old position index to the current one

        # get the index of the current time stamp
        curr_idx = np.where(curr_merge[0, 0] == curr_pos_range[:, 0])[0]
        # if there is a matching time stamp, put the corresponding value into the merge slice
        if curr_idx.size:
            curr_merge[0, 1] = curr_pos_range[curr_idx, 1].copy()   # enter the position value into the merge slice
            last_pos = curr_pos_range[curr_idx, 1].copy()           # update the last known position value
            new_pos += 1                                            # move sliding window
        # else, put in the last known position value
        else:
            curr_merge[0, 1] = last_pos

        #### look for correct encoder time step ###
        # if encoder window has to be updated, re-select the current range of encoder values

        if new_enc != old_enc:
            if new_enc+3 < encoder.shape[0]:
                curr_enc_range = encoder[new_enc-3:new_enc+3, :].copy()
            else:
                curr_enc_range = encoder[new_enc-3:, :].copy()
        old_enc = new_enc        # update old encoder index to the current one

        # get the index of the current time stamp
        curr_idx = np.where(curr_merge[0, 0] == curr_enc_range[:, 0])[0]
        # if there is a matching time stamp, put the corresponding value into the merge slice
        if curr_idx.size:
            curr_merge[0, 4] = curr_enc_range[curr_idx[0], 1].copy()   # enter the encoder value into the merge slice
            last_enc = curr_enc_range[curr_idx[0], 1].copy()           # update the last known encoder value
            new_enc += 1                                            # move sliding window
        # else, put in the last known encoder value
        else:
            curr_merge[0, 4] = last_enc

        #### look for correct trigger time step ###
        # look at adjacent time points, if they are less than 0.5 ms apart, take the maximum (1 if there was a frame during that time)
        # check if the sliding window moved and it has to be updated
        if new_trig != old_trig:
            if new_trig+3 < trigger.shape[0]:
                curr_trig_range = trigger[new_trig-3:new_trig+3, :].copy()
            else:
                curr_trig_range = trigger[new_trig-3:, :].copy()
        old_trig = new_trig        # update old trigger index to the current one

        # check if the current sliding window has time stamps between the current merge time stamps
        curr_idx = np.where((curr_merge[0, 0] <= curr_trig_range[:, 0]) & (curr_trig_range[:, 0] < curr_merge[1, 0]))[0]

        if curr_idx.size:
            curr_merge[0, 2] = max(curr_trig_range[curr_idx, 1])
            curr_merge[0, 3] = max(curr_trig_range[curr_idx, 2])
            new_trig = new_trig + curr_idx.size
            last_lick = max(curr_trig_range[curr_idx, 1])
        else:
            curr_merge[0, 2] = last_lick
            curr_merge[0, 3] = 0

        # put the aligned data back into the main merge array
        merge[i] = curr_merge[0].copy()
        if verbose:
            progress(i, merge.shape[0] - 1, status='Aligning behavioral data...')

    # Fix frame count by appending/prepending frames
    if imaging:
        if frames_to_prepend > 0:
            first_frame = np.where(merge[:, 3] == 1)[0][0]
            first_frame_trig = np.where(raw_trig[:, 2] == 1)[0][0]
            median_frame_time = int(np.median([len(frame) for frame in trig_blocks]))
            if median_frame_time > 70:
                median_frame_time = 66
            if first_frame > frames_to_prepend * median_frame_time:
                # if frames would fit in the merge array before the first recorded frame, prepend them with proper steps
                # make a list of the new indices (in steps of median_frame_time before the first frame)
                idx_start = first_frame - frames_to_prepend * median_frame_time
                idx_list = np.arange(start=idx_start, stop=first_frame, step=median_frame_time)
                if idx_list.shape[0] != frames_to_prepend:
                    print(f'Frame correction failed for {trig_path}!')
                    return None, None
                merge[idx_list, 3] = 1
                if verbose:
                    print(f'Imported frame count missed {frames_to_prepend}, corrected.')
            # else, if trigger and position stop at the same time point (0.2s difference) and the time is right to fit
            # frame_count frames with a frame rate maximally deviating from the median frame time by 2 ms/frame,
            # create regular frame count indices and replace original ones with it
            elif abs(trigger[-1, 0] - position[-1, 0]) < 0.2:

                # if the first frame is known (after at least 35ms) take this index, otherwise put first frame at 0
                if first_frame_trig > 70:
                    start_frame = first_frame_trig
                else:
                    start_frame = 0
                frame_idx, spacing = np.linspace(start_frame, merge.shape[0] - 2, num=frame_count,
                                                 retstep=True, dtype=int)
                if abs(median_frame_time-spacing) < 4:
                    merge[:, 3] = 0
                    merge[frame_idx, 3] = 1
            # if frames dont fit, and we dont have a good start-end-period, and less than 30 frames missing,
            # put them in steps of 2 equally in the start and end
            elif frames_to_prepend < 30:
                for i in range(frames_to_prepend):
                    if i % 2 == 0:  # for every even step, put the frame in the beginning
                        if merge[i*2, 3] != 1:
                            merge[i*2, 3] = 1
                        else:
                            merge[i+1 * 2, 3] = 1
                    else:       # for every uneven step, put the frame in the end
                        if merge[-(i*2), 3] != 1:
                            merge[-(i*2), 3] = 1
                        else:
                            merge[-((i+1)*2), 3] = 1
                if verbose:
                    print(f'Imported frame count missed {frames_to_prepend}, corrected.')
            else:
                # correction does not work if the whole log file is not large enough to include all missing frames
                print(f'{int(abs(more_frames_in_TDT))} too few frames imported from TDT, could not be corrected.')
                with open(r'W:\Neurophysiology-Storage1\Wahl\Hendrik\PhD\Data\Batch2\bad_trials.txt', 'a') as bad_file:
                    out = bad_file.write(f'{trig_path}\t{more_frames_in_TDT}\n')
                return None, None

    end = timer()
    if verbose:
        print('Actual processing time for this trial: {0:.2f} s'.format(end-start))

    # clean up file: remove redundant first time stamps, remove last time stamp, reset time stamps
    if imaging:
        merge = np.delete(merge, range(np.where(merge[:, 3] == 1)[0][0]), 0)
    merge = np.delete(merge, merge.shape[0] - 1, 0)
    merge[:, 0] = merge[:, 0] - merge[0, 0]
    merge[:, 0] = [floor(x * 100000) / 100000 for x in merge[:, 0]]

    # translate encoder data into velocity [cm/s] if enc_unit = 'speed'
    if enc_unit == 'speed':
        sample_rate = 0.008                                      # sample rate of encoder in s (default 0.008 s or 8 ms)
        d_wheel = 10.5                                           # wheel diameter in cm (default 10.5 cm)
        n_ticks = 1436                                           # number of ticks in a full wheel rotation
        deg_dist = (d_wheel*np.pi)/n_ticks                       # distance in cm the band moves for each encoder tick
        speed = -merge[:, 4] * deg_dist/sample_rate               # speed in cm/s for each sample
        speed[speed == -0] = 0
        merge = np.c_[merge, speed]

    # check frame count again
    if imaging and np.sum(merge[:, 3]) != frame_count:
        print(f'Frame count matching unsuccessful: \n{np.sum(merge[:, 3])} frames in merge, should be {frame_count} frames.')
        return None, None

    return merge, (end-start)


def align_behavior_files(enc_path, pos_path, trig_path, log_path, imaging=False, frame_count=None, enc_unit='speed', verbose=False):
    """
    Main function that aligns behavioral data from three text files to a common master time frame provided by LabView.
    Data are re-sampled at the rate of the data type with the highest sampling rate (TDT, 2 kHz). Missing values of data
    with lower sampling rate are filled in based on their last available value.
    :param enc_path: str, path to the Encoder.txt file (running speed)
    :param pos_path: str, path to the TCP.txt file (VR position)
    :param trig_path: str, path to the TDT.txt file (licking and frame trigger)
    :param log_path: str, path to the LOG.txt file of this session (water reward times)
    :param imaging: bool flag whether the behavioral data is accompanied by an imaging movie
    :param frame_count: int, frame count of the imaging movie (if imaging=True)
    :param enc_unit: str, if 'speed', encoder data is translated into cm/s; otherwise raw encoder data in
                     rotation [degrees] / sample window (8 ms) is saved
    :param verbose: bool flag whether status updates should be printed into the console (progress bar not affected)
    :return: merge, np.array with columns [time stamp - position - licks - frame - encoder]
    """

    pd.options.mode.chained_assignment = None   # Disable false positive SettingWithCopyWarning

    # Load behavioral files
    encoder = load_file(enc_path)
    position = load_file(pos_path)
    trigger = load_file(trig_path)
    raw_trig = trigger.copy()

    try:
        # Separate licking and trigger signals (different start times)
        licking = trigger[:, :2].copy()
        licking[0, 0] = licking[0, 1]
        licking[0, 1] = encoder[0, 1]
        trigger = np.delete(trigger, 1, axis=1)
    except IndexError:
        # catch error if a file is empty
        print('File seems to be empty, alignment skipped.')
        return None


    data = [trigger, licking, encoder, position]

    if imaging and frame_count is None:
        print(f'Error in trial {enc_path}: provide frame count if imaging=True!')
        return None, None

    # check if the trial might be incomplete (VR not run until the end or TDT file incomplete)
    if max(position[:, 1]) < 110 or abs(position[-1, 0] - trigger[-1, 0]) > 2:
        print('Trial incomplete, please remove file!')
        with open(r'W:\Neurophysiology-Storage1\Wahl\Hendrik\PhD\Data\Batch2\bad_trials.txt', 'a') as bad_file:
            out = bad_file.write(f'{trig_path}\n')
        return None

    ### check if a file was copied from the previous one (bug in LabView), if the start time stamp differs by >2s
    # transform the integer time stamps plus the date from the TDT file into datetime objects
    time_format = '%Y%m%d%H%M%S%f'
    date = trig_path.split('_')[-2]
    for f in data:
        start_time = f'{int(f[0, 0]):09}'
        if start_time[4:] == '60000':
            f[0, 0] -= 1
    start_times = np.array([datetime.strptime(date+f'{int(x[0, 0]):09}', time_format) for x in data])

    # calculate absolute difference in seconds between the start times
    max_diff = np.max(np.abs(start_times[:, None] - start_times)).total_seconds()
    if max_diff > 2:
        print(f'Faulty trial (TDT file copied from previous trial), time stamps differed by {int(max(max_diff))}s!')
        with open(r'W:\Neurophysiology-Storage1\Wahl\Hendrik\PhD\Data\Batch2\bad_trials.txt', 'a') as bad_file:
            out = bad_file.write(f'{trig_path}\tTDT from previous trial, diff {int(max(max_diff))}s\n')
        return None

    ### preprocess frame trigger signal
    if imaging:
        frames_to_prepend = 0
        # get a list of indices for every time stamp a frame was acquired
        trig_blocks = np.split(np.where(trigger[1:, 1])[0]+1, np.where(np.diff(np.where(trigger[1:, 1])[0]) != 1)[0]+1)
        # take the middle of each frame acquisition as the unique time stamp of that frame, save trigger idx in a list
        trig_idx = []
        for block in trig_blocks:
            trigger[block, 1] = 0  # set the whole period to 0
            if np.isnan(np.mean(block)):
                print(f'No frame trigger in {trig_path}. Check file!')
                # return None, None
            trigger[int(round(np.mean(block))), 1] = 1
            trig_idx.append(int(round(np.mean(block))))

        # check if imported frame trigger matches frame count of .tif file and try to fix it
        more_frames_in_TDT = int(np.sum(trigger[1:, 1]) - frame_count)  # pos if TDT, neg if .tif had more frames
        if more_frames_in_TDT == 0 and verbose:
            print('Frame count matched, no correction necessary.')
        elif more_frames_in_TDT < 0:
            # first check if TDT has been logging shorter than TCP
            tdt_offset = position[-1, 0] - trigger[-1, 0]
            # if all missing frames would fit in the offset (time where tdt was not logging), print out warning
            if tdt_offset / 0.033 > abs(more_frames_in_TDT):
                print('TDT not logging long enough, too long trial? Check trial!')
            # if TDT file had too little frames, they are assumed to have been recorded before TDT logging
            # these frames are added after merge array has been filled
            frames_to_prepend = abs(more_frames_in_TDT)

        elif more_frames_in_TDT > 0:
            # if TDT included too many frames, its assumed that the false-positive frames are from the end of recording
            if more_frames_in_TDT < 5:
                for i in range(more_frames_in_TDT):
                    trigger[trig_blocks[-i], 1] = 0
            else:
                print(f'{more_frames_in_TDT} too many frames imported from TDT, could not be corrected!')
                with open(r'W:\Neurophysiology-Storage1\Wahl\Hendrik\PhD\Data\Batch2\bad_trials.txt', 'a') as bad_file:
                    out = bad_file.write(f'{trig_path}\n')
                return None

        if frames_to_prepend > 0:
            first_frame = np.where(trigger[1:, 1] == 1)[0][0]+1
            first_frame_start = np.where(raw_trig[:, 2] == 1)[0][0]
            median_frame_time = int(np.median([len(frame) for frame in trig_blocks]))
            if median_frame_time > 70:
                median_frame_time = 66
            if first_frame > frames_to_prepend * median_frame_time:
                # if frames would fit in the merge array before the first recorded frame, prepend them with proper steps
                # make a list of the new indices (in steps of median_frame_time before the first frame)
                idx_start = first_frame - frames_to_prepend * median_frame_time
                # add 1 to indices because we do not count the first index of the trigger signal
                idx_list = np.arange(start=idx_start+1, stop=first_frame, step=median_frame_time)
                if idx_list.shape[0] != frames_to_prepend:
                    print(f'Frame correction failed for {trig_path}!')
                    return None
                trigger[idx_list, 1] = 1
                if verbose:
                    print(f'Imported frame count missed {frames_to_prepend}, corrected by prepending them to the'
                          f'start of the file in 30Hz distances.')

            # if frames dont fit, and less than 30 frames missing, put them in steps of 2 equally in the start and end
            elif frames_to_prepend < 30:
                for i in range(1, frames_to_prepend+1):
                    if i % 2 == 0:  # for every even step, put the frame in the beginning
                        if trigger[i * 2, 1] != 1:
                            trigger[i * 2, 1] = 1
                        else:
                            trigger[i + 2 * 2, 1] = 1
                    else:  # for every uneven step, put the frame in the end
                        if trigger[-(i * 2), 1] != 1:
                            trigger[-(i * 2), 1] = 1
                        else:
                            trigger[-((i + 1) * 2), 1] = 1
                if verbose:
                    print(f'Imported frame count missed {frames_to_prepend}, corrected by adding frames regularly'
                          f'at start and end of file.')
            else:
                # correction does not work if the whole log file is not large enough to include all missing frames
                print(f'{int(abs(more_frames_in_TDT))} too few frames imported from TDT, could not be corrected.')
                with open(r'W:\Neurophysiology-Storage1\Wahl\Hendrik\PhD\Data\Batch2\bad_trials.txt', 'a') as bad_file:
                    out = bad_file.write(f'{trig_path}\t{more_frames_in_TDT}\n')
                return None

    ### Preprocess position signal
    pos_to_be_del = np.arange(np.argmax(position[:, 1])+1, position.shape[0])  # Get indices after the max position
    position = np.delete(position, pos_to_be_del, 0)  # remove all data points after maximum position (end of corridor)
    position[position[:, 1] < -10, 1] = -10           # cap position values to -10 and 110
    position[position[:, 1] > 110, 1] = 110
    data[3] = position                                # Put preprocessed positions back into data list

    # Transform relative time to absolute time for all measurements
    fixed_times = []
    for idx, dataset in enumerate(data):
        timesteps = np.array([start_times[idx] + timedelta(seconds=x) for x in dataset[1:, 0]])
        fixed_times.append(np.array([timesteps, dataset[1:, 1]]).T)

    # Transform data to pandas dataframes with timestamps indices
    datasets = ['trigger', 'licking', 'encoder', 'position']
    df_list = []
    for name, dataset in zip(datasets, fixed_times):
        df = pd.DataFrame(dataset[:, 1], index=dataset[:, 0], columns=[name])
        df_list.append(df)

    # Serially merge dataframes by the time stamp of the trigger (highest sampling rate)
    merge = pd.merge_asof(df_list[0], df_list[1], left_index=True, right_index=True)
    merge = pd.merge_asof(merge, df_list[2], left_index=True, right_index=True)
    merge = pd.merge_asof(merge, df_list[3], left_index=True, right_index=True)

    # Load LOG file TODO maybe make another boolean column with "being in reward zone"
    if log_path is not None:
        log = pd.read_csv(log_path, sep='\t', parse_dates=[[0, 1]])
        # Filter out bad lines if Datetime column could not be parsed
        if log['Date_Time'].dtype == 'object':
            log = log.loc[~np.isnan(log['Trial'])]
            log['Date_Time'] = pd.to_datetime(log['Date_Time'])
        # Extract data for the current trial based on the first and last times of the trigger timestamps
        trial_log = log.loc[(log['Date_Time'] > merge.index[0]) & (log['Date_Time'] < merge.index[-1])]
        # Get times when the valve opened
        water_times = trial_log.loc[trial_log['Event'].str.contains('Dev1/port0/line0-B'), 'Date_Time']
        # Initialize empty water column and set to '1' for every water valve opening timestamp
        merge['water'] = 0
        for water_time in water_times:
            merge.loc[merge.index[merge.index.get_loc(water_time, method='nearest')], 'water'] = 1
    else:
        merge['water'] = -1

    # Delete rows before the first frame (dont delete anything if no frame trigger)
    if merge['trigger'].sum() > 0:
        first_frame = merge.index[np.where(merge['trigger'] == 1)[0][0]]
    else:
        first_frame = merge.index[0]
    merge_filt = merge[merge.index >= first_frame]

    # Fill in NaN values
    merge_filt['position'].fillna(-10, inplace=True)
    merge_filt['encoder'].fillna(0, inplace=True)
    merge_filt['licking'].fillna(0, inplace=True)

    # Set proper data types (float for position, int for the rest)
    merge_filt['trigger'] = merge_filt['trigger'].astype(int)
    merge_filt['licking'] = merge_filt['licking'].astype(int)
    merge_filt['encoder'] = merge_filt['encoder'].astype(int)

    # translate encoder data into velocity [cm/s] if enc_unit = 'speed'
    if enc_unit == 'speed':
        sample_rate = 0.008                                      # sample rate of encoder in s (default 0.008 s or 8 ms)
        d_wheel = 10.5                                           # wheel diameter in cm (default 10.5 cm)
        n_ticks = 1436                                           # number of ticks in a full wheel rotation
        deg_dist = (d_wheel*np.pi)/n_ticks                       # distance in cm the band moves for each encoder tick
        speed = -merge_filt.loc[:, 'encoder'] * deg_dist/sample_rate               # speed in cm/s for each sample
        speed[speed == -0] = 0
        merge_filt['speed'] = speed

    # check frame count again
    merge_trig = np.sum(merge_filt['trigger'])
    if imaging and merge_trig != frame_count:
        print(f'Frame count matching unsuccessful: \n{merge_trig} frames in merge, should be {frame_count} frames.')
        return None

    # transform back to numpy array for saving
    time_passed = merge_filt.index - merge_filt.index[0]                                        # transfer timestamps to
    seconds = np.array(time_passed.total_seconds())                                             # time change in seconds
    array_df = merge_filt[['position', 'licking', 'trigger', 'encoder', 'speed', 'water']]      # change column order
    array = np.hstack((seconds[..., np.newaxis], np.array(array_df)))                           # combine both arrays

    return array
