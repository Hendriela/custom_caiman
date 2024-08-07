#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Created on 03/11/2023 09:26
@author: hheise

"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
import os

from preprint import data_cleaning as dc
from preprint import placecell_heatmap_transition_functions as func


def quantify_place_cell_transitions(pf_list, pc_list, align_days=False, day_diff=3, shuffle=None, avg_mat=False):

    def get_adjusted_cell_counts(class_arr):
        counts = np.bincount(class_arr)[1:]
        if len(counts) == 1:
            counts = np.append(counts, values=0)
        elif len(counts) == 2:
            pass
        else:
            return
        return counts

    pc_transitions = []

    for mouse_idx, mouse in enumerate(pc_list):

        mouse_id = list(mouse.keys())[0]
        # if mouse_id == '63_1':
        #     break
        # Extract data and align days if necessary
        rel_days = np.array(mouse[mouse_id][1])

        if align_days:
            if 3 not in rel_days:
                rel_days[(rel_days == 2) | (rel_days == 4)] = 3
            rel_days[(rel_days == 5) | (rel_days == 6) | (rel_days == 7)] = 6
            rel_days[(rel_days == 8) | (rel_days == 9) | (rel_days == 10)] = 9
            rel_days[(rel_days == 11) | (rel_days == 12) | (rel_days == 13)] = 12
            rel_days[(rel_days == 14) | (rel_days == 15) | (rel_days == 16)] = 15
            rel_days[(rel_days == 17) | (rel_days == 18) | (rel_days == 19)] = 18
            rel_days[(rel_days == 20) | (rel_days == 21) | (rel_days == 22)] = 21
            rel_days[(rel_days == 23) | (rel_days == 24) | (rel_days == 25)] = 24
            if 28 not in rel_days:
                rel_days[(rel_days == 26) | (rel_days == 27) | (rel_days == 28)] = 27
            rel_sess = np.arange(len(rel_days)) - np.argmax(np.where(rel_days <= 0, rel_days, -np.inf))
            rel_days[(-5 < rel_sess) & (rel_sess < 1)] = np.arange(-np.sum((-5 < rel_sess) & (rel_sess < 1)) + 1, 1)

        pc_data = mouse[mouse_id][0]
        pc_data = pd.DataFrame(pc_data, columns=rel_days)
        pf_data = pf_list[mouse_idx][mouse_id][0]
        pf_data.columns = rel_days
        pf_data = pf_data.reset_index().drop(columns=['index'])     # Use continuous index that matches pc_data

        # Ignore day 1
        rel_days = rel_days[rel_days != 1]
        pf_data = pf_data.loc[:, pf_data.columns != 1]
        pc_data = pc_data.loc[:, pc_data.columns != 1]

        if shuffle is not None:
            iterations = shuffle
        else:
            iterations = 1

        pc_trans = {'pre': np.zeros((iterations, 3, 3)), 'early': np.zeros((iterations, 3, 3)), 'late': np.zeros((iterations, 3, 3))}
        stable_pc_trans = {'pre': np.zeros((iterations, 4, 4)), 'early': np.zeros((iterations, 4, 4)), 'late': np.zeros((iterations, 4, 4))}
        kld_pcs = {'pre': [], 'early': [], 'late': []}
        kld_ncs = {'pre': [], 'early': [], 'late': []}

        for i in range(iterations):

            rng = np.random.default_rng()   # Initialize the random generator

            # Loop through days and get place cell transitions between sessions that are 3 days apart
            for day_idx, day in enumerate(rel_days):

                next_day_idx = np.where(rel_days == day + day_diff)[0]

                # If a session 3 days later exists, get place cell transitions
                if len(next_day_idx) == 1:

                    # General PC - non-PC transitions
                    # Add 1 to the pc data to include "Lost" cells
                    day1_pc = pc_data.iloc[:, day_idx].to_numpy() + 1
                    day1_pc = np.nan_to_num(day1_pc).astype(int)
                    day2_pc = pc_data.iloc[:, next_day_idx].to_numpy().squeeze() + 1
                    day2_pc = np.nan_to_num(day2_pc).astype(int)

                    if shuffle is not None:

                        # mat_true = func.transition_matrix(mask1=day1_pc, mask2=day2_pc, num_classes=3, percent=False)
                        # mat_shuff = []
                        # for i in range(shuffle):
                        #     day2_pc_shuff = np.random.default_rng().permutation(day2_pc)
                        #     mat_shuff.append(func.transition_matrix(mask1=day1_pc, mask2=day2_pc_shuff, num_classes=3, percent=False))
                        # mat = np.stack(mat_shuff)

                        mat = func.transition_matrix(mask1=rng.permutation(day1_pc), mask2=day2_pc,
                                                     num_classes=3, percent=False)

                        # mat_shuff_mean = np.mean(mat_shuff, axis=0)
                        #
                        # # Plot shuffled distribution and true value
                        # nrows = mat_true.shape[0]
                        # ncols = mat_true.shape[1]
                        # fig, ax = plt.subplots(nrows=nrows, ncols=ncols)
                        # for i in range(nrows):
                        #     for j in range(ncols):
                        #         # sns.violinplot(y=mat_shuff[:, i, j], ax=ax[i, j], cut=0)
                        #         sns.stripplot(y=mat_shuff[:, i, j], ax=ax[i, j], alpha=0.5)
                        #         ax[i, j].axhline(mat_true[i, j], color='red')
                        #         perc = (np.sum(mat_shuff[:, i, j] < mat_true[i, j]) / len(mat_shuff[:, i, j])) * 100
                        #         ax[i, j].text(0.05, 0.95, perc, transform=ax[i, j].transAxes, verticalalignment='top',
                        #                       horizontalalignment='left')
                    else:
                        mat = func.transition_matrix(mask1=day1_pc, mask2=day2_pc, num_classes=3, percent=False)

                    # Compute Kullback-Leibler divergence for each day separately (from cell class frequencies)
                    day2_counts = get_adjusted_cell_counts(day2_pc)
                    if day2_counts is None:
                        raise IndexError(f'Wrong number of classes in M{mouse_id}, day {day}.')

                    q_arr = day2_counts / day2_counts.sum()  # Exclude lost cells

                    if np.sum(day1_pc == 2) <= 3:   # If the previous day had 3 place cells or less, we ignore this session pair
                        kld_pc = np.nan
                        kld_nc = np.nan
                    else:
                        class_counts_pc = get_adjusted_cell_counts(day2_pc[day1_pc == 2])
                        class_counts_nc = get_adjusted_cell_counts(day2_pc[day1_pc == 1])

                        pc_arr = class_counts_pc / class_counts_pc.sum()
                        nc_arr = class_counts_nc / class_counts_nc.sum()

                        kld_pc = np.sum([n1 * np.log2(n1 / n2) if n1 > 0 else 0 for n1, n2 in zip(pc_arr.flatten(), q_arr.flatten())])
                        kld_nc = np.sum([n1 * np.log2(n1 / n2) if n1 > 0 else 0 for n1, n2 in zip(nc_arr.flatten(), q_arr.flatten())])

                    if rel_days[next_day_idx] <= 0:
                        pc_trans['pre'][i] = pc_trans['pre'][i] + mat
                        kld_pcs['pre'].append(kld_pc)
                        kld_ncs['pre'].append(kld_nc)
                        # print(f'Day {rel_days[next_day_idx]} sorted under "Pre"')

                    elif rel_days[next_day_idx] <= 7:
                        pc_trans['early'][i] = pc_trans['early'][i] + mat
                        kld_pcs['early'].append(kld_pc)
                        kld_ncs['early'].append(kld_nc)
                        # print(f'Day {rel_days[next_day_idx]} sorted under "Early"')

                    else:
                        pc_trans['late'][i] = pc_trans['late'][i] + mat
                        kld_pcs['late'].append(kld_pc)
                        kld_ncs['late'].append(kld_nc)
                        # print(f'Day {rel_days[next_day_idx]} sorted under "Late"')

                    # Split PC-PC into stable (pf_idx overlap) and unstable PC transitions
                    pc_pc_idx = (day1_pc + day2_pc) == 4
                    pf1 = pf_data.loc[pc_pc_idx].iloc[:, day_idx]
                    pf2 = pf_data.loc[pc_pc_idx].iloc[:, next_day_idx[0]]

                    for row_idx in pf1.index:
                        pf_1 = pf1.loc[row_idx]
                        pf_2 = pf2.loc[row_idx]

                        overlapping_pf = False
                        for place_field_1 in pf_1:
                            for place_field_2 in pf_2:
                                if np.any([i in place_field_1 for i in place_field_2]):
                                    overlapping_pf = True

                        if overlapping_pf:
                            # Class 3 means that the place cell retains at least one place field
                            day1_pc[row_idx] = 3
                            day2_pc[row_idx] = 3

                    mat = func.transition_matrix(mask1=day1_pc, mask2=day2_pc, num_classes=4, percent=False)
                    if rel_days[next_day_idx] <= 0:
                        stable_pc_trans['pre'][i] = stable_pc_trans['pre'][i] + mat
                    elif rel_days[next_day_idx] <= 7:
                        stable_pc_trans['early'][i] = stable_pc_trans['early'][i] + mat
                    else:
                        stable_pc_trans['late'][i] = stable_pc_trans['late'][i] + mat

        if avg_mat:
            pc_trans = {k: np.nanmean(v, axis=0) for k, v in pc_trans.items()}
            stable_pc_trans = {k: np.nanmean(v, axis=0) for k, v in stable_pc_trans.items()}

        # Average KLDs across periods
        kld_pc = {k: np.nanmean(v, axis=0) for k, v in kld_pcs.items()}
        kld_nc = {k: np.nanmean(v, axis=0) for k, v in kld_ncs.items()}


        pc_transitions.append(pd.DataFrame([dict(mouse_id=int(mouse_id.split('_')[0]),
                                                 pc_pre=pc_trans['pre'].squeeze(), pc_early=pc_trans['early'].squeeze(), pc_late=pc_trans['late'].squeeze(),
                                                 stab_pc_pre=stable_pc_trans['pre'].squeeze(), stab_pc_early=stable_pc_trans['early'].squeeze(), stab_pc_late=stable_pc_trans['late'].squeeze(),
                                                 kld_pc_pre=kld_pc['pre'], kld_pc_early=kld_pc['early'], kld_pc_late=kld_pc['late'],
                                                 kld_nc_pre=kld_nc['pre'], kld_nc_early=kld_nc['early'], kld_nc_late=kld_nc['late'])]))

    return pd.concat(pc_transitions, ignore_index=True)


def transition_matrix_to_prism(matrix_df: pd.DataFrame, phase, include_lost=False, with_stable=False, norm='rows'):

    if with_stable:
        col = f'stab_pc_{phase}'
    else:
        col = f'pc_{phase}'

    dicts = []
    for _, row in matrix_df.iterrows():
        if include_lost:
            if norm in ['rows', 'forward']:
                mat = row[col] / np.sum(row[col], axis=1)[..., np.newaxis] * 100
            elif norm in ['cols', 'backward']:
                mat = row[col] / np.sum(row[col], axis=0) * 100
            elif norm in ['all']:
                mat = row[col] / np.sum(row[col]) * 100
            else:
                raise NotImplementedError

            ### Include "lost"
            if with_stable:
                dicts.append(dict(trans='lost > lost', mouse_id=row['mouse_id'], perc=mat[0, 0]))
                dicts.append(dict(trans='lost > non-coding', mouse_id=row['mouse_id'], perc=mat[0, 1]))
                dicts.append(dict(trans='lost > remapped', mouse_id=row['mouse_id'], perc=mat[0, 2]))
                dicts.append(dict(trans='lost > stable', mouse_id=row['mouse_id'], perc=mat[0, 3]))
                dicts.append(dict(trans='non-coding > lost', mouse_id=row['mouse_id'], perc=mat[1, 0]))
                dicts.append(dict(trans='non-coding > non-coding', mouse_id=row['mouse_id'], perc=mat[1, 1]))
                dicts.append(dict(trans='non-coding > remapped', mouse_id=row['mouse_id'], perc=mat[1, 2]))
                dicts.append(dict(trans='non-coding > place_cell', mouse_id=row['mouse_id'], perc=mat[1, 3]))
                dicts.append(dict(trans='remapped > lost', mouse_id=row['mouse_id'], perc=mat[2, 0]))
                dicts.append(dict(trans='remapped > non-coding', mouse_id=row['mouse_id'], perc=mat[2, 1]))
                dicts.append(dict(trans='remapped > remapped', mouse_id=row['mouse_id'], perc=mat[2, 2]))
                dicts.append(dict(trans='remapped > stable', mouse_id=row['mouse_id'], perc=mat[2, 3]))
                dicts.append(dict(trans='stable > lost', mouse_id=row['mouse_id'], perc=mat[3, 0]))
                dicts.append(dict(trans='stable > non-coding', mouse_id=row['mouse_id'], perc=mat[3, 1]))
                dicts.append(dict(trans='stable > unstable', mouse_id=row['mouse_id'], perc=mat[3, 2]))
                dicts.append(dict(trans='stable > stable', mouse_id=row['mouse_id'], perc=mat[3, 3]))
            else:
                dicts.append(dict(trans='lost > lost', mouse_id=row['mouse_id'], perc=mat[0, 0]))
                dicts.append(dict(trans='lost > non-coding', mouse_id=row['mouse_id'], perc=mat[0, 1]))
                dicts.append(dict(trans='lost > place_cell', mouse_id=row['mouse_id'], perc=mat[0, 2]))
                dicts.append(dict(trans='non-coding > lost', mouse_id=row['mouse_id'], perc=mat[1, 0]))
                dicts.append(dict(trans='non-coding > non-coding', mouse_id=row['mouse_id'], perc=mat[1, 1]))
                dicts.append(dict(trans='non-coding > place_cell', mouse_id=row['mouse_id'], perc=mat[1, 2]))
                dicts.append(dict(trans='place_cell > lost', mouse_id=row['mouse_id'], perc=mat[2, 0]))
                dicts.append(dict(trans='place_cell > non-coding', mouse_id=row['mouse_id'], perc=mat[2, 1]))
                dicts.append(dict(trans='place_cell > place_cell', mouse_id=row['mouse_id'], perc=mat[2, 2]))

        else:
            if norm in ['rows', 'forward']:
                mat = row[col][1:, 1:] / np.sum(row[col][1:, 1:], axis=1)[..., np.newaxis] * 100
            elif norm in ['cols', 'backward']:
                mat = row[col][1:, 1:] / np.sum(row[col][1:, 1:], axis=0) * 100
            elif norm in ['all']:
                mat = row[col][1:, 1:] / np.sum(row[col][1:, 1:]) * 100
            else:
                raise NotImplementedError

            ### Exclude "lost"
            if with_stable:
                dicts.append(dict(trans='non-coding > non-coding', mouse_id=row['mouse_id'], perc=mat[0, 0]))
                dicts.append(dict(trans='non-coding > remapped', mouse_id=row['mouse_id'], perc=mat[0, 1]))
                dicts.append(dict(trans='non-coding > stable', mouse_id=row['mouse_id'], perc=mat[0, 2]))
                dicts.append(dict(trans='remapped > non-coding', mouse_id=row['mouse_id'], perc=mat[1, 0]))
                dicts.append(dict(trans='remapped > remapped', mouse_id=row['mouse_id'], perc=mat[1, 1]))
                dicts.append(dict(trans='remapped > stable', mouse_id=row['mouse_id'], perc=mat[1, 2]))
                dicts.append(dict(trans='stable > non-coding', mouse_id=row['mouse_id'], perc=mat[2, 0]))
                dicts.append(dict(trans='stable > remapped', mouse_id=row['mouse_id'], perc=mat[2, 1]))
                dicts.append(dict(trans='stable > stable', mouse_id=row['mouse_id'], perc=mat[2, 2]))
            else:
                dicts.append(dict(trans='non-coding > non-coding', mouse_id=row['mouse_id'], perc=mat[0, 0]))
                dicts.append(dict(trans='non-coding > place_cell', mouse_id=row['mouse_id'], perc=mat[0, 1]))
                dicts.append(dict(trans='place_cell > non-coding', mouse_id=row['mouse_id'], perc=mat[1, 0]))
                dicts.append(dict(trans='place_cell > place_cell', mouse_id=row['mouse_id'], perc=mat[1, 1]))

    df = pd.DataFrame(dicts).pivot(index='trans', columns='mouse_id', values='perc')
    if with_stable:
        if norm in ['rows', 'forward']:
            df = df.reindex(['non-coding > non-coding', 'non-coding > remapped', 'non-coding > stable',
                             'remapped > non-coding', 'remapped > remapped', 'remapped > place_cell',
                             'place_cell > non-coding', 'place_cell > remapped', 'place_cell > place_cell'])
        elif norm in ['cols', 'backward']:
            df = df.reindex(['non-coding > non-coding', 'remapped > non-coding', 'stable > non-coding',
                             'non-coding > remapped', 'remapped > remapped', 'stable > remapped',
                             'non-coding > stable', 'remapped > stable', 'stable > stable'])
        elif norm in ['all']:
            df = df.reindex(['non-coding > non-coding', 'non-coding > remapped', 'non-coding > stable',
                             'remapped > non-coding', 'remapped > remapped', 'remapped > place_cell',
                             'place_cell > non-coding', 'place_cell > remapped', 'place_cell > place_cell'])
    else:
        if norm in ['rows', 'forward']:
            df = df.reindex(['non-coding > non-coding', 'non-coding > place_cell',
                             'place_cell > non-coding', 'place_cell > place_cell'])
        elif norm in ['cols', 'backward']:
            df = df.reindex(['non-coding > non-coding', 'place_cell > non-coding',
                             'non-coding > place_cell', 'place_cell > place_cell'])
        elif norm in ['all']:
            df = df.reindex(['non-coding > non-coding', 'non-coding > place_cell',
                             'place_cell > non-coding', 'place_cell > place_cell'])

    return df


def compute_kullback_leibler_div(dist_true, dist_rng, include_lost=False, with_stable=False, pc_direction=None):
    """ Compute Kullback-Leibler-Divergence of True and Shuffled transition distributions. """

    def preprocess_matrix(arr, incl_lost, pc_dir):
        """ Filters and normalizes a transition matrix. """
        if not incl_lost:
            arr = arr[1:, 1:]

        if pc_dir is not None:
            if pc_direction == 'backward':
                arr = arr[:, -1:]
            elif pc_direction == 'forward':
                arr = arr[-1:]
            else:
                raise ValueError(f'PC direction of {pc_direction} is undefined.')

        # Transform counts to probabilities
        return arr / arr.sum(), arr.sum()

    # Define which columns of the dataframes to use
    cols = list(dist_true.columns[1:4])
    if with_stable:
        cols = ['stab_'+col for col in cols]

    # Perform computation row-wise (for each mouse) and column-wise (for each phase)
    kl_df = []
    for row_idx in range(len(dist_true)):
        for phase in cols:

            # Extract transition matrices
            true_arr, n_cells_true = preprocess_matrix(dist_true.loc[row_idx, phase], incl_lost=include_lost, pc_dir=pc_direction)
            rng_arr, n_cells_rng = preprocess_matrix(dist_rng.loc[row_idx, phase], incl_lost=include_lost, pc_dir=pc_direction)

            # Compute Kullback-Leibler divergence between true and shuffled distributions
            # If the observed probability P(x) is 0, also the contribution of that transition is 0
            kld = np.sum([n1 * np.log2(n1 / n2) if n1 > 0 else 0 for n1, n2 in zip(true_arr.flatten(), rng_arr.flatten())])
            kl_df.append(pd.DataFrame([dict(mouse_id=dist_true.loc[row_idx, 'mouse_id'], phase=phase.split('_')[-1],
                                            kld=kld, n_cells_true=n_cells_true, n_cells_rng=n_cells_rng)]))
    return pd.concat(kl_df)


def compute_kld_without_shuffling(dist):
    """ Compute Kullback-Leibler-Divergence of all vs only PC/NC transitions. """

    # Define which columns of the dataframes to use
    cols = list(dist.columns[1:4])

    # Perform computation row-wise (for each mouse) and column-wise (for each phase)
    kl_df = []
    for row_idx in range(len(dist)):
        for phase in cols:

            # Default distribution: Probabilities of a cell being a NC or PC, irrespective of previous function (equal to occurrence)
            q_arr = np.sum(dist.loc[row_idx, phase][1:, 1:], axis=0) / np.sum(dist.loc[row_idx, phase][1:, 1:])
            # Test distribution 1: Probabilities of a cell being a NC or PC, given that the cell was a PC the day before
            n_cells_pc = dist.loc[row_idx, phase][2, 1:].sum()
            pc_arr = dist.loc[row_idx, phase][2, 1:] / n_cells_pc
            # Test distribution 2: Probabilities of a cell being a NC or PC, given that the cell was a NC the day before
            nc_arr = dist.loc[row_idx, phase][1, 1:] / dist.loc[row_idx, phase][1, 1:].sum()

            # Compute Kullback-Leibler divergence between both distributions
            # If the observed probability P(x) is 0, also the contribution of that transition is 0
            kld_pc = np.sum([n1 * np.log2(n1 / n2) if n1 > 0 else 0 for n1, n2 in zip(pc_arr.flatten(), q_arr.flatten())])
            kld_nc = np.sum([n1 * np.log2(n1 / n2) if n1 > 0 else 0 for n1, n2 in zip(nc_arr.flatten(), q_arr.flatten())])

            kl_df.append(pd.DataFrame([dict(mouse_id=dist.loc[row_idx, 'mouse_id'], phase=phase.split('_')[-1],
                                            kld_pc=kld_pc, kld_nc=kld_nc, n_pc=n_cells_pc)]))
    return pd.concat(kl_df)


def compute_kld_per_session(pc_list, align_days=False, day_diff=3, n_iter=1000, pc_limit=3):

    def get_adjusted_cell_counts(class_arr):
        counts = np.bincount(class_arr)[1:]
        if len(counts) == 1:
            counts = np.append(counts, values=0)
        elif len(counts) == 2:
            pass
        else:
            return
        return counts

    pc_transitions = []

    for mouse_idx, mouse in enumerate(pc_list):

        mouse_id = list(mouse.keys())[0]
        # if mouse_id == '63_1':
        #     break
        # Extract data and align days if necessary
        rel_days = np.array(mouse[mouse_id][1])

        if align_days:
            if 3 not in rel_days:
                rel_days[(rel_days == 2) | (rel_days == 4)] = 3
            rel_days[(rel_days == 5) | (rel_days == 6) | (rel_days == 7)] = 6
            rel_days[(rel_days == 8) | (rel_days == 9) | (rel_days == 10)] = 9
            rel_days[(rel_days == 11) | (rel_days == 12) | (rel_days == 13)] = 12
            rel_days[(rel_days == 14) | (rel_days == 15) | (rel_days == 16)] = 15
            rel_days[(rel_days == 17) | (rel_days == 18) | (rel_days == 19)] = 18
            rel_days[(rel_days == 20) | (rel_days == 21) | (rel_days == 22)] = 21
            rel_days[(rel_days == 23) | (rel_days == 24) | (rel_days == 25)] = 24
            if 28 not in rel_days:
                rel_days[(rel_days == 26) | (rel_days == 27) | (rel_days == 28)] = 27
            rel_sess = np.arange(len(rel_days)) - np.argmax(np.where(rel_days <= 0, rel_days, -np.inf))
            rel_days[(-5 < rel_sess) & (rel_sess < 1)] = np.arange(-np.sum((-5 < rel_sess) & (rel_sess < 1)) + 1, 1)

        pc_data = mouse[mouse_id][0]
        pc_data = pd.DataFrame(pc_data, columns=rel_days)

        # Ignore day 1
        rel_days = rel_days[rel_days != 1]
        pc_data = pc_data.loc[:, pc_data.columns != 1]

        kld_all = {'pre': [], 'early': [], 'late': []}
        kld_pcs = {'pre': [], 'early': [], 'late': []}
        kld_ncs = {'pre': [], 'early': [], 'late': []}

        # Loop through days and get place cell transitions between sessions that are 3 days apart
        for day_idx, day in enumerate(rel_days):

            next_day_idx = np.where(rel_days == day + day_diff)[0]

            # If a session 3 days later exists, get place cell transitions
            if len(next_day_idx) == 1:

                # General PC - non-PC transitions
                # Add 1 to the pc data to include "Lost" cells
                day1_pc = pc_data.iloc[:, day_idx].to_numpy() + 1
                day1_pc = np.nan_to_num(day1_pc).astype(int)
                day2_pc = pc_data.iloc[:, next_day_idx].to_numpy().squeeze() + 1
                day2_pc = np.nan_to_num(day2_pc).astype(int)

                ### Compute Kullback-Leibler divergence for each day separately (from cell class frequencies)
                day2_counts = get_adjusted_cell_counts(day2_pc)
                if day2_counts is None:
                    raise IndexError(f'Wrong number of classes in M{mouse_id}, day {day}.')

                q_arr = day2_counts / day2_counts.sum()  # Exclude lost cells

                if np.sum(day1_pc == 2) <= pc_limit:   # If the previous day had "pc_limit" place cells or less, we ignore this session pair
                    kld_pc = np.nan
                    kld_nc = np.nan
                    kld_total = np.nan
                else:
                    class_counts_pc = get_adjusted_cell_counts(day2_pc[day1_pc == 2])
                    class_counts_nc = get_adjusted_cell_counts(day2_pc[day1_pc == 1])

                    if class_counts_pc is None or np.sum(q_arr == 0) > 0:
                        kld_pc = np.nan
                    else:
                        pc_arr = class_counts_pc / class_counts_pc.sum()
                        kld_pc = np.sum([n1 * np.log2(n1 / n2) if n1 > 0 else 0 for n1, n2 in
                                         zip(pc_arr.flatten(), q_arr.flatten())])

                    if class_counts_nc is None or np.sum(q_arr == 0) > 0:
                        kld_nc = np.nan
                    else:
                        nc_arr = class_counts_nc / class_counts_nc.sum()
                        kld_nc = np.sum([n1 * np.log2(n1 / n2) if n1 > 0 else 0 for n1, n2 in zip(nc_arr.flatten(), q_arr.flatten())])

                    ### Compute Kullback-Leibler divergence for all transitions simultaneously against shuffling
                    mat = func.transition_matrix(mask1=day1_pc, mask2=day2_pc, num_classes=3, percent=False)[1:, 1:]
                    mat_rng = np.empty((n_iter, *mat.shape))
                    for i in range(n_iter):
                        mat_rng[i] = func.transition_matrix(mask1=np.random.permutation(day1_pc), mask2=day2_pc, num_classes=3, percent=False)[1:, 1:]
                    mat_rng = np.mean(mat_rng, axis=0)

                    mat_freq = mat / mat.sum()
                    mat_rng_freq = mat_rng / mat_rng.sum()
                    if np.sum(mat_rng_freq == 0) > 0:
                        kld_total = np.nan
                    else:
                        kld_total = np.sum([n1 * np.log2(n1 / n2) if n1 > 0 else 0 for n1, n2 in zip(mat_freq.flatten(), mat_rng_freq.flatten())])

                if rel_days[next_day_idx] <= 0:
                    kld_pcs['pre'].append(kld_pc)
                    kld_ncs['pre'].append(kld_nc)
                    kld_all['pre'].append(kld_total)
                    # print(f'Day {rel_days[next_day_idx]} sorted under "Pre"')

                elif rel_days[next_day_idx] <= 7:
                    kld_pcs['early'].append(kld_pc)
                    kld_ncs['early'].append(kld_nc)
                    kld_all['early'].append(kld_total)
                    # print(f'Day {rel_days[next_day_idx]} sorted under "Early"')

                else:
                    kld_pcs['late'].append(kld_pc)
                    kld_ncs['late'].append(kld_nc)
                    kld_all['late'].append(kld_total)
                    # print(f'Day {rel_days[next_day_idx]} sorted under "Late"')

        # Average KLDs across periods
        kld_pc = {k: np.nanmean(v, axis=0) for k, v in kld_pcs.items()}
        kld_nc = {k: np.nanmean(v, axis=0) for k, v in kld_ncs.items()}
        kld_all = {k: np.nanmean(v, axis=0) for k, v in kld_all.items()}

        pc_transitions.append(pd.DataFrame([dict(mouse_id=int(mouse_id.split('_')[0]),
                                                 kld_pc_pre=kld_pc['pre'], kld_pc_early=kld_pc['early'], kld_pc_late=kld_pc['late'],
                                                 kld_nc_pre=kld_nc['pre'], kld_nc_early=kld_nc['early'], kld_nc_late=kld_nc['late'],
                                                 kld_all_pre=kld_all['pre'], kld_all_early=kld_all['early'], kld_all_late=kld_all['late'])]))

    return pd.concat(pc_transitions, ignore_index=True)



def plot_shuffled_data(true_df, rng_df, stable=False, norm=None, include_lost=False, statistic='percentile',
                       directory=None):

    if stable:
        prefix = 'stab_pc_'
    else:
        prefix = 'pc_'

    for (idx_true, row_true), (idx_rng, row_rng) in zip(true_df.iterrows(), rng_df.iterrows()):

        # Prepare data
        if include_lost:
            true_mat = [row_true[f'{prefix}pre'], row_true[f'{prefix}early'], row_true[f'{prefix}late']]
            rng_mat = [row_rng[f'{prefix}pre'], row_rng[f'{prefix}early'], row_rng[f'{prefix}late']]
            x = ['lost > lost', 'lost> non-coding', 'lost > place_cell',
                 'non-coding > lost', 'non-coding > non-coding', 'non-coding > place_cell',
                 'place_cell > lost', 'place_cell > non-coding', 'place_cell > place_cell']
        else:
            true_mat = [row_true[f'{prefix}pre'][1:, 1:], row_true[f'{prefix}early'][1:, 1:], row_true[f'{prefix}late'][1:, 1:]]
            rng_mat = [row_rng[f'{prefix}pre'][:, 1:, 1:], row_rng[f'{prefix}early'][:, 1:, 1:], row_rng[f'{prefix}late'][:, 1:, 1:]]
            x = ['non-coding > non-coding', 'non-coding > place_cell',
                 'place_cell > non-coding', 'place_cell > place_cell']

        # Normalize data
        if norm in ['rows', 'row', 'forward']:
            true = [((mat / np.nansum(mat, axis=1)[..., np.newaxis]) * 100).flatten() for mat in true_mat]
            rng = [((mat / np.nansum(mat, axis=2)[..., np.newaxis]) * 100).flatten() for mat in rng_mat]
        elif norm in ['cols', 'col', 'backward']:
            true = [((mat / np.nansum(mat, axis=0)) * 100).flatten() for mat in true_mat]
            rng = [((mat / np.nansum(mat, axis=1)[:, np.newaxis, :]) * 100).flatten() for mat in rng_mat]
        elif norm in ['all']:
            true = [((mat / np.nansum(mat)) * 100).flatten() for mat in true_mat]
            rng = [((mat / np.nansum(mat, axis=(1, 2))[:, np.newaxis, np.newaxis]) * 100).flatten() for mat in rng_mat]
        else:
            true = [mat.flatten() for mat in true_mat]
            rng = [mat.flatten() for mat in rng_mat]

        # Create plot (one per mouse)
        df_true = pd.DataFrame(data=true, index=['pre', 'early', 'late'], columns=x)
        df_rng = pd.DataFrame(data={x[i]: np.hstack([lys[i::4] for lys in rng]) for i in range(len(x))},
                              index=[*['pre']*len(rng_mat[0]), *['early']*len(rng_mat[0]), *['late']*len(rng_mat[0])])
        df_rng.index.name = 'phase'
        df_rng = df_rng.reset_index()
        df_rng_melt = df_rng.melt(id_vars='phase', value_name='cell_count', var_name='transition')
        if norm is not None:
            df_rng_melt.dropna(inplace=True)
            df_rng_melt.replace(np.inf, 100, inplace=True)
            df_rng_melt.replace(-np.inf, 0, inplace=True)

        # Compute one-sample t-test between true and rng distributions for each transition
        df_p = df_true.copy()
        df_p[:] = np.nan
        for phase_id, phase in df_rng.groupby('phase'):
            for transition in phase.columns:
                if transition != 'phase':

                    y_true = df_true.loc[phase_id, transition]
                    y_rng = phase.loc[:, transition]

                    # Using scipy.stats (seems to greatly overestimate significance)
                    res = stats.ttest_1samp(a=y_rng, popmean=y_true)

                    # Get percentile of true value within shuffled distribution
                    perc = np.sum(y_true >= y_rng) / len(y_rng)

                    # ChatGPT suggestion, does not really work: Manually comparing against percentiles
                    # Determine the critical values for your chosen significance level (e.g., 0.05)
                    differences = np.abs(y_true - y_rng)
                    alpha = 0.05
                    critical_value_lower = np.percentile(differences, 100 * alpha / 2)
                    critical_value_upper = np.percentile(differences, 100 * (1 - alpha / 2))

                    # Count how many differences fall below the lower critical value and above the upper critical value
                    num_below = np.sum(differences < critical_value_lower)
                    num_above = np.sum(differences > critical_value_upper)

                    # Calculate the two-tailed p-value
                    p_value = (num_below + num_above) / len(differences)

                    if statistic == 'ttest':
                        df_p.at[phase_id, transition] = perc
                    elif statistic == 'chatgpt':
                        df_p.at[phase_id, transition] = p_value
                    elif statistic == 'percentile':
                        df_p.at[phase_id, transition] = perc
                    else:
                        raise ValueError(f'Statistic value "{statistic}" not understood.')

        g = sns.FacetGrid(df_rng_melt, row='phase', col='transition', margin_titles=True, sharey='col', sharex='row',
                          height=3, aspect=2)
        # g.map(sns.violinplot, 'transition', 'cell_count', inner='stick', cut=0)
        g.map_dataframe(sns.stripplot, y="cell_count")

        # g.set_xlabels([])
        # Add true data, p-value and x-label to each facet
        for (row_val, col_val), ax in g.axes_dict.items():
            if row_val == 'late':
                ax.set_xlabel(col_val)
            else:
                ax.set_xlabel("")
            ax.axhline(df_true.loc[row_val, col_val], color='red', linestyle='--')
            ax.text(0.05, 0.05, f'p={df_p.loc[row_val, col_val]:.3f}', transform=ax.transAxes)

        g.fig.subplots_adjust(top=0.92)  # adjust the Figure to make space for title
        g.fig.suptitle(f'M{row_true.mouse_id}')

        if directory is not None:
            plt.savefig(os.path.join(directory, f"place_cell_transitions_chance_levels_M{row_true.mouse_id}.png"))
            plt.close()


#%% Function calls
pf_idx = dc.load_data('pf_idx')
is_pc = dc.load_data('is_pc')

pc_transition_old = quantify_place_cell_transitions(pf_list=pf_idx, pc_list=is_pc)
pc_transition = quantify_place_cell_transitions(pf_list=pf_idx, pc_list=is_pc, align_days=True)
# Many iterations (>500) is needed to get at least one of the more unlikely transitions)
pc_transition_rng_1 = quantify_place_cell_transitions(pf_list=pf_idx, pc_list=is_pc, shuffle=1000, avg_mat=True, align_days=True)


transition_matrix_to_prism(matrix_df=pc_transition, phase='late', include_lost=False, with_stable=False,
                           norm='forward').to_clipboard(index=True, header=True)
transition_matrix_to_prism(matrix_df=pc_transition_rng, phase='late', include_lost=False, with_stable=False,
                           norm='forward').to_clipboard(index=True, header=True)

plot_shuffled_data(true_df=pc_transition, rng_df=pc_transition_rng, directory=r'W:\Helmchen Group\Neurophysiology-Storage-01\Wahl\Hendrik\PhD\Papers\preprint\class_quantification\place_cell_transitions')


"""
Without shuffling: Compare frequencies of D2 classes (PC/NC) with frequencies of D2 classes only of cells that were PC/NC before
"""

# Kullback-Leibler divergence between true and shuffled distributions
kl_div = compute_kullback_leibler_div(dist_true=pc_transition, dist_rng=pc_transition_rng_1, pc_direction='forward')
kl_div.pivot(index='phase', columns='mouse_id', values='kld').loc[['pre', 'early', 'late']].to_clipboard(index=True, header=True)
kl_div.pivot(index='mouse_id', columns='phase', values='n_cells_true').to_clipboard(index=True, header=True)

# Kullback-Leibler divergence between all and only PC/NC cells
kl_div = compute_kld_without_shuffling(dist=pc_transition)
kl_div.pivot(index='phase', columns='mouse_id', values='kld_nc').loc[['pre', 'early', 'late']].to_clipboard(index=True, header=True)
kl_div.pivot(index='mouse_id', columns='phase', values='n_cells_true').to_clipboard(index=True, header=True)

# Kullback-Leibler divergence computed for each session pair separately
kld_df = pc_transition[['mouse_id', 'kld_pc_pre', 'kld_pc_early', 'kld_pc_late']]
kld_df_long = kld_df.melt(id_vars='mouse_id', value_vars=['kld_pc_pre', 'kld_pc_early', 'kld_pc_late'])
kld_df_long.pivot(index='variable', columns='mouse_id', values='value').loc[['kld_pc_pre', 'kld_pc_early', 'kld_pc_late']].to_clipboard(index=True, header=True)

# Kullback-Leibler divergence computed for each session pair separately, against shuffled for all transitions
kl_div = compute_kld_per_session(pc_list=is_pc, align_days=True, n_iter=1000, pc_limit=0)
kl_div_long = kl_div.melt(id_vars='mouse_id', value_vars=['kld_all_pre', 'kld_all_early', 'kld_all_late'])
kl_div_long.pivot(index='variable', columns='mouse_id', values='value').loc[['kld_all_pre', 'kld_all_early', 'kld_all_late']].to_clipboard(index=True, header=True)
