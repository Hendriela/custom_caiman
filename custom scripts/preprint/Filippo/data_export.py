#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Created on 18/07/2023 13:07
@author: hheise

"""
import numpy as np
import pandas as pd
import os
import pickle
import seaborn as sns
import matplotlib.pyplot as plt
from datetime import datetime

import common_hist
from schema import common_mice, common_img, common_match, hheise_behav, hheise_hist, hheise_placecell
from util import helper
import functools

os.chdir('.\\custom scripts\\preprint\\Filippo')
#%% Request on 18.07.

# VR Performance over time
no_deficit = [93, 91, 95]
no_deficit_flicker = [111, 114, 116]
recovery = [33, 83, 85, 86, 89, 90, 113]
deficit_no_flicker = [41, 63, 69] #, 121]
deficit_flicker = [108, 110] #, 112]
sham_injection = [115, 122]
mice = [*no_deficit, *no_deficit_flicker, *recovery, *deficit_no_flicker, *deficit_flicker, *sham_injection]

dfs = []
for mouse in mice:
    # Get day of surgery
    surgery_day = (common_mice.Surgery() & 'surgery_type="Microsphere injection"' & f'mouse_id={mouse}').fetch(
        'surgery_date')[0].date()
    # Get date and performance for each session before the surgery day
    res = {'username': "hheise",  'mouse_id': mouse}
    days = (hheise_behav.VRPerformance & res & f'day<"2022-09-09"').fetch('day')
    perf_lick = (hheise_behav.VRPerformance & res & f'day<"2022-09-09"').get_mean('binned_lick_ratio')
    perf_si = (hheise_behav.VRPerformance & res & f'day<"2022-09-09"').get_mean('si_binned_run')
    perf_dist = (hheise_behav.VRPerformance & res & f'day<"2022-09-09"').get_mean('distance')
    perf_si_raw = (hheise_behav.VRPerformanceTest & res & f'day<"2022-09-09"').get_mean('si_raw_run')
    perf_si_norm = (hheise_behav.VRPerformanceTest & res & f'day<"2022-09-09"').get_mean('si_norm_run')

    pc_ratios = pd.DataFrame((hheise_placecell.PlaceCell & f'mouse_id={mouse}' & 'corridor_type=0' & 'place_cell_id=2').fetch('day', 'place_cell_ratio', as_dict=True))

    # Transform dates into days before surgery
    rel_days = np.array([(d - surgery_day).days for d in days])

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

    rel_days[rel_sess < 1] = np.arange(-np.sum(rel_sess < 1)+1, 1)

    df_wide = pd.DataFrame(dict(mouse_id=mouse, days=days, rel_days=rel_days, rel_sess=rel_sess, blr=perf_lick, si=perf_si,
                                dist=perf_dist, si_raw=perf_si_raw, si_norm=perf_si_norm))
    df_wide['rel_sess'] = df_wide.index - np.argmax(np.where(df_wide['rel_days'] <= 0, df_wide['rel_days'], -np.inf))

    df_melt = df_wide.melt(id_vars=['mouse_id', 'days', 'rel_days', 'rel_sess'], var_name='metric', value_name='perf')

    met_norm = []
    for metric in df_melt['metric'].unique():
        met = df_melt[df_melt['metric'] == metric]
        met_norm.append(list(met['perf'] / met[(met['rel_sess'] >= -2) & (met['rel_sess'] <= 0)]['perf'].mean()))
    met_norm = [item for sublist in met_norm for item in sublist]
    df_melt['perf_norm'] = met_norm
    dfs.append(df_melt)


df = pd.concat(dfs, ignore_index=True)
df.sort_values(by=['mouse_id', 'metric'], inplace=True, ignore_index=True)
df.to_csv('.\\20230718\\vr_performance_aligned.csv', sep=',')

# Correlate performance metrics
df_perf = df[['mouse_id', 'days', 'rel_days', 'metric', 'perf']].pivot(columns='metric', values='perf', index=['mouse_id', 'rel_days'])
fig, ax = plt.subplots(nrows=1, ncols=3, layout='constrained')
ax[0] = sns.regplot(df_perf, x='si', y='si_norm', ax=ax[0])
ax[0].set_box_aspect(1)
ax[0].set_xlabel('si')
ax[0].set_ylabel('si_norm')
ax[1] = sns.regplot(df_perf, x='si', y='si_raw', ax=ax[1])
ax[1].set_box_aspect(1)
ax[1].set_xlabel('si')
ax[1].set_ylabel('si_raw')
ax[2] = sns.regplot(df_perf, x='si_raw', y='si_norm', ax=ax[2])
ax[2].set_box_aspect(1)
ax[2].set_xlabel('si_raw')
ax[2].set_ylabel('si_norm')
fig.suptitle('Raw performance values', fontsize=16)

# VR Performance for 2D scatter plot
# take "datas" from behavior_matrix.py
datas[0]['si_binned_run'].to_csv('.\\20230718\\si_scatterplot_norm.csv', sep=',')
datas[1]['si_binned_run'].to_csv('.\\20230718\\si_scatterplot_raw.csv', sep=',')

### Histo data
inj_volume = pd.DataFrame((common_mice.Injection & 'substance_name="microspheres"' & f'mouse_id in {helper.in_query(mice)}').fetch('mouse_id', 'volume', as_dict=True)).rename(columns={'volume': 'inj_volume'})
spheres_extrap = pd.DataFrame((hheise_hist.MicrosphereSummary.Metric & 'metric_name="spheres"' & f'mouse_id in {helper.in_query(mice)}').fetch('mouse_id', 'count_extrap', as_dict=True)).rename(columns={'count_extrap': 'spheres_extrap'})
spheres = pd.DataFrame((hheise_hist.MicrosphereSummary.Metric & 'metric_name="spheres"' & f'mouse_id in {helper.in_query(mice)}').fetch('mouse_id', 'count', as_dict=True)).rename(columns={'count': 'spheres'})
lesion = pd.DataFrame((hheise_hist.MicrosphereSummary.Metric & 'metric_name="auto"' & f'mouse_id in {helper.in_query(mice)}').fetch('mouse_id', 'count', as_dict=True)).rename(columns={'count': 'autofluo'})
lesion_extrap = pd.DataFrame((hheise_hist.MicrosphereSummary.Metric & 'metric_name="auto"' & f'mouse_id in {helper.in_query(mice)}').fetch('mouse_id', 'count_extrap', as_dict=True)).rename(columns={'count_extrap': 'autofluo_extrap'})

df_merged = functools.reduce(lambda left, right: pd.merge(left, right, on=['mouse_id'], how='outer'), [spheres_extrap, spheres, lesion_extrap, lesion, inj_volume])
df_merged.to_csv('.\\20230718\\histology.csv', sep=',')

# PC data (stable/unstable) over time
stability_classes.to_csv('.\\20230718\\pc_distribution_without_lost.csv', sep=',')

# PC ratios over time
dfs = []
for mouse in mice:
    # Get day of surgery
    surgery_day = (common_mice.Surgery() & 'surgery_type="Microsphere injection"' & f'mouse_id={mouse}').fetch(
        'surgery_date')[0].date()
    # Get date and performance for each session before the surgery day
    pc_ratios = pd.DataFrame((hheise_placecell.PlaceCell & f'mouse_id={mouse}' & 'corridor_type=0' & 'day<"2022-09-09"'
                              & 'place_cell_id=2').fetch('mouse_id', 'day', 'place_cell_ratio', as_dict=True))
    n_pcs = pd.DataFrame((hheise_placecell.PlaceCell.ROI & f'mouse_id={mouse}' & 'corridor_type=0' & 'day<"2022-09-09"' & 'place_cell_id=2' & 'is_place_cell').fetch('day'))[0].value_counts()
    n_pcs = pd.DataFrame({'day': n_pcs.index, 'n_pcs': n_pcs.values})
    pc_ratios['rel_days'] = [(d - surgery_day).days for d in pc_ratios['day']]
    pc_ratios['place_cell_ratio'] *= 100
    pc_ratio1 = pd.merge(pc_ratios, n_pcs, how='outer', on='day')
    dfs.append(pc_ratio1)
pc_ratios = pd.concat(dfs, ignore_index=True)
pc_ratios.sort_values(by=['mouse_id', 'rel_days'], inplace=True, ignore_index=True)
pc_ratios.fillna(0, inplace=True)
pc_ratios.to_csv('.\\20230718\\pc_ratios.csv', sep=',')

#%% Request on 26.07.2023

# Binary licks for each mouse/session

dfs = []
for mouse in mice:

    # Get day of surgery
    surgery_day = (common_mice.Surgery() & 'surgery_type="Microsphere injection"' & f'mouse_id={mouse}').fetch(
        'surgery_date')[0].date()

    # Get binary lick data
    pks = (hheise_behav.VRPerformance & 'username="hheise"' & f'mouse_id={mouse}').fetch('KEY')
    binary_licks = []
    for key in pks:
        trials = (hheise_behav.VRSession & key).get_normal_trials()
        # Bin licking data from these trials into one array and binarize per-trial
        data = [(hheise_behav.VRSession.VRTrial & key & f'trial_id={idx}').get_binned_licking(bin_size=1) for idx in
                trials]
        data = np.vstack(data)
        # data[data > 0] = 1  # we only care about that a bin had a lick, not how many
        binary_licks.append(data)

    # Transform dates into days before surgery
    rel_days = np.array([(pk['day'] - surgery_day).days for pk in pks])

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

    rel_days[(-5 < rel_sess) & (rel_sess < 1)] = np.arange(-4, 1)

    df_wide = pd.DataFrame(dict(mouse_id=mouse, days=[pk['day'] for pk in pks], rel_days=rel_days, rel_sess=rel_sess, licks=binary_licks))

    dfs.append(df_wide)

df = pd.concat(dfs, ignore_index=True)

df = df[df['rel_sess'] >= -4]
df = df[df['rel_days'] != 1]
df = df[df['rel_days'] != 2]
df = df[df['rel_days'] != 4]
df = df[df['rel_sess'] <= 9]

df_filt = df[['mouse_id', 'rel_days', 'licks']]
df_pivot = df_filt.pivot(columns='rel_days', index='mouse_id', values='licks')

df_pivot.to_pickle('.\\20230726\\absolute_bin_licks.pickle')

#%% Sphere location

def clean_dataframe(old_df, mice_ids):

    # Only keep mice that are included in mice_ids
    new_df = old_df[old_df['mouse_id'].isin(mice_ids)]
    new_rows = []

    # Find mice that dont have a value for all regions and enter dummy data (zeros)
    for region in new_df.region.unique():
        for mouse in mice_ids:
            if mouse not in new_df[new_df['region'] == region]['mouse_id']:
                if mouse < 108:
                    dummy_data = np.zeros(10)
                else:
                    dummy_data = np.array([0, 0, np.nan, np.nan, np.nan, np.nan, 0, 0, np.nan, np.nan])
                dummy_data = np.append(dummy_data, [region, mouse])

                new_rows.append(pd.DataFrame(dummy_data.reshape(1, -1), columns=list(new_df)))

    if len(new_rows) > 0:
        new_df = pd.concat([new_df, pd.concat(new_rows, ignore_index=True)], ignore_index=True)

    new_df = new_df[new_df['mouse_id'] != '63']
    new_df = new_df[new_df['mouse_id'] != '69']
    new_df_sort = new_df.sort_values(by=['region', 'mouse_id'], ignore_index=True)

    conversion = {col: (str if col in ['region', 'mouse_id'] else float) for col in new_df_sort.columns}
    new_df_sort = new_df_sort.astype(conversion)

    return new_df_sort

# Non-summed locations
mic = pd.DataFrame(hheise_hist.Microsphere().fetch('mouse_id', 'hemisphere', 'structure_id', 'lesion', 'spheres', as_dict=True))
sum_spheres_df = mic.groupby(['mouse_id', 'hemisphere', 'structure_id', 'lesion']).agg({'spheres': 'sum'}).reset_index()
sum_spheres_df.loc[sum_spheres_df['mouse_id'] >= 108, 'lesion'] = np.nan
sum_spheres_df['acronym'] = [(common_hist.Ontology & f'structure_id={id_}').fetch1('acronym') for id_ in sum_spheres_df['structure_id']]
sum_spheres_df['full_name'] = [(common_hist.Ontology & f'structure_id={id_}').fetch1('full_name') for id_ in sum_spheres_df['structure_id']]
sum_spheres_df = sum_spheres_df[sum_spheres_df['mouse_id'] != 94]
sum_spheres_df.to_csv('.\\20230726\\raw_locations.csv', sep=',', index=False)

# Summed locations
columns = ['spheres', 'spheres_rel', 'spheres_lesion', 'spheres_lesion_rel', 'lesion_vol', 'lesion_vol_rel',
           'spheres_extrap', 'spheres_rel_extrap', 'spheres_lesion_extrap', 'spheres_lesion_rel_extrap',
           'region', 'mouse_id']

# Old grouping
df = hheise_hist.Microsphere().get_structure_groups(grouping={'cognitive': ['HPF', 'PL', 'ACA', 'ILA', 'RSP', 'PERI'],
                                                              'neocortex': ['FRP', 'MO', 'OLF', 'SS', 'GU', 'VISC',
                                                                            'AUD', 'VIS', 'ORB', 'AI', 'PTLp', 'TEa',
                                                                            'ECT'],
                                                              'thalamus': ['TH'],
                                                              'basal_ganglia': ['CP', 'ACB', 'FS', 'LSX', 'sAMY', 'PAL'],
                                                              'brainstem': ['MB', 'HB']},
                                                    columns=columns)
df = clean_dataframe(df, mice)
df.to_csv('.\\20230726\\old_grouping.csv', sep=',', index=False)

# Hippocampal formation
df = hheise_hist.Microsphere().get_structure_groups(grouping={'hippocampus': ['HPF'],
                                                              'cortex': ['Isocortex', 'OLF'],
                                                              'thalamus': ['TH'],
                                                              'cerebral_nuclei': ['CNU'],
                                                              'brainstem': ['MB', 'HB'],
                                                              'white_matter': ['fiber tracts']},
                                                    columns=columns)
df = clean_dataframe(df, mice)
df.to_csv('.\\20230726\\hippocampus.csv', sep=',', index=False)

# Only Hippocampal formation
df = hheise_hist.Microsphere().get_structure_groups(grouping={'hippocampal_formation': ['HPF']},
                                                    columns=columns)
df = clean_dataframe(df, mice)
df.to_csv('.\\20230726\\hippocampal_formation.csv', sep=',', index=False)

# Hippocampal subregions
df = hheise_hist.Microsphere().get_structure_groups(grouping={'subiculum': ['SUB', 'PRE', 'PAR', 'POST'],
                                                              'entorhinal': ['ENT'],
                                                              'dentate_gyrus': ['DG'],
                                                              'ca1': ['CA1'],
                                                              'ca2': ['CA2'],
                                                              'ca3': ['CA3'],
                                                              },
                                                    columns=columns)
df = clean_dataframe(df, mice)
df.to_csv('.\\20230726\\hippocampal_subregions.csv', sep=',', index=False)

# Silasi grouping
df = hheise_hist.Microsphere().get_structure_groups(grouping={'hippocampus': ['HPF'],
                                                              'white_matter': ['fiber tracts'],
                                                              'striatum': ['STR'],
                                                              'thalamus': ['TH'],
                                                              'neocortex': ['Isocortex'],
                                                              },
                                                    columns=columns)
df = clean_dataframe(df, mice)
df.to_csv('.\\20230726\\literature.csv', sep=',', index=False)

# Functional grouping (?)
df = hheise_hist.Microsphere().get_structure_groups(grouping={'hippocampus': ['HIP'],
                                                              'retrohippocampus': ['RHP'],
                                                              'association': ['ECT', 'PERI', 'TEa', 'PTLp', 'RSP'],
                                                              'mPFC': ['PL', 'ACA', 'ILA'],
                                                              'Insular': ['AI']},
                                                    columns=columns)
df = clean_dataframe(df, mice)
df.to_csv('.\\20230726\\cognitive.csv', sep=',', index=False)

# Other regions
df = hheise_hist.Microsphere().get_structure_groups(grouping={'cortex': ['CTXpl'],
                                                              'amygdala': ['CTXsp'],
                                                              'thalamus': ['TH'],
                                                              'striatum': ['CNU'],
                                                              'hypothalamus': ['HY'],
                                                              'midbrain': ['MB'],
                                                              'hindbrain': ['HB'],
                                                              'white_matter': ['fiber tracts']},
                                                    columns=columns, include_other=False)
df = clean_dataframe(df, mice)
df.to_csv('.\\20230726\\others.csv', sep=',', index=False)

#%% NEURAL DATA

def save_dict(dic, fname):
    with open(f'{fname}.pkl', 'wb') as file:
        pickle.dump(dic, file)

# Cell-matched data
queries = (
           (common_match.MatchedIndex & 'mouse_id=33'),       # 407 cells
           # (common_match.MatchedIndex & 'mouse_id=38'),
           (common_match.MatchedIndex & 'username="hheise"' & 'mouse_id=41'),   # 246 cells
           (common_match.MatchedIndex & 'username="hheise"' & 'mouse_id=63' & 'day<="2021-03-23"'),     # 350 cells
           (common_match.MatchedIndex & 'username="hheise"' & 'mouse_id=69' & 'day<="2021-03-23"'),     # 350 cells
           (common_match.MatchedIndex & 'username="hheise"' & 'mouse_id=83'),   # 270 cells
           (common_match.MatchedIndex & 'username="hheise"' & 'mouse_id=85'),   # 250 cells
           (common_match.MatchedIndex & 'username="hheise"' & 'mouse_id=86'),   # 86 cells
           (common_match.MatchedIndex & 'username="hheise"' & 'mouse_id=89'),   # 183 cells
           (common_match.MatchedIndex & 'username="hheise"' & 'mouse_id=90'),   # 131 cells
           (common_match.MatchedIndex & 'username="hheise"' & 'mouse_id=91'),   # 299 cells
           (common_match.MatchedIndex & 'username="hheise"' & 'mouse_id=93'),   # 397 cells
           (common_match.MatchedIndex & 'username="hheise"' & 'mouse_id=95'),   # 350 cells
           (common_match.MatchedIndex & 'username="hheise"' & 'mouse_id=108' & 'day<"2022-09-09"'),     # 316 cells
           (common_match.MatchedIndex & 'username="hheise"' & 'mouse_id=110' & 'day<"2022-09-09"'),     # 218 cells
           (common_match.MatchedIndex & 'username="hheise"' & 'mouse_id=111' & 'day<"2022-09-09"'),     # 201 cells
           (common_match.MatchedIndex & 'username="hheise"' & 'mouse_id=113' & 'day<"2022-09-09"'),     # 350 cells
           (common_match.MatchedIndex & 'username="hheise"' & 'mouse_id=114' & 'day<"2022-09-09"'),     # 307 cells
           (common_match.MatchedIndex & 'username="hheise"' & 'mouse_id=115' & 'day<"2022-09-09"'),     # 331 cells
           (common_match.MatchedIndex & 'username="hheise"' & 'mouse_id=116' & 'day<"2022-09-09"'),     # 350 cells
           (common_match.MatchedIndex & 'username="hheise"' & 'mouse_id=122' & 'day<"2022-09-09"'),     # 401 cells
           (common_match.MatchedIndex & 'username="hheise"' & 'mouse_id=121' & 'day<"2022-09-09"'),     # 791 cells
)

match_matrices = [query.construct_matrix() for query in queries]
is_pc = common_match.MatchedIndex().load_matched_data(match_queries=queries, data_type='is_place_cell', relative_dates=False)
pfs = common_match.MatchedIndex().load_matched_data(match_queries=queries, data_type='place_field_idx')
spatial_maps = common_match.MatchedIndex().load_matched_data(match_queries=queries, data_type='bin_spikerate')
spat_dff_maps = common_match.MatchedIndex().load_matched_data(match_queries=queries, data_type='bin_activity')
dff = common_match.MatchedIndex().load_matched_data(match_queries=queries, data_type='dff', as_array=False)
decon = common_match.MatchedIndex().load_matched_data(match_queries=queries, data_type='decon')
coords = common_match.MatchedIndex().load_matched_data(match_queries=queries, data_type='com')
pf_com = common_match.MatchedIndex().load_matched_data(match_queries=queries, data_type='place_field_com')
pf_sd = common_match.MatchedIndex().load_matched_data(match_queries=queries, data_type='place_field_sd')

decon = {k: v.applymap(lambda x: x.astype(np.float16) if type(x) == np.ndarray else x) for k, v in decon.items()}
dff = {k: v.applymap(lambda x: x.astype(np.float16) if type(x) == np.ndarray else x) for k, v in dff.items()}

# Save session strings for analysed sessions for each mouse
session_strings = pd.DataFrame({m: {'session': list(v[1])} for m, v in is_pc.items()}).T.explode('session').reset_index(names='mouse_id')
session_strings.to_csv(r'C:\Users\hheise.UZH\PycharmProjects\Caiman\custom scripts\preprint\Filippo\neural_data\session_strings.csv')

save_dict(is_pc, 'neural_data\\is_pc')
save_dict(pfs, 'neural_data\\place_field_idx')
save_dict(spatial_maps, 'neural_data\\spatial_activity_maps_spikerate')
save_dict(spat_dff_maps, 'neural_data\\spatial_activity_maps_dff')
save_dict(dff, 'neural_data\\dff')
save_dict(decon, 'neural_data\\decon')
save_dict(coords, 'neural_data\\cell_coords')
save_dict(pf_com, 'neural_data\\pf_com')
save_dict(pf_sd, 'neural_data\\pf_sd')


# Stability classes
from preprint import stable_unstable_classification as suc
from preprint import data_cleaning as dc

with open(os.path.join(r'C:\Users\hheise.UZH\PycharmProjects\Caiman\custom scripts\preprint\Filippo\neural_data',
                       f'is_pc.pkl'), 'rb') as file:
    is_pc = pickle.load(file)

spatial_maps = dc.load_data('spat_dff_maps')
is_pc_old = dc.load_data('is_pc')

stability_classes = suc.classify_stability(is_pc_list=is_pc_old, spatial_map_list=spatial_maps, for_prism=False,
                                           ignore_lost=True, align_days=True)

stability_classes_neurons = {}
stability_classes_neurons_aligned = {}
for mouse_str, mouse_data in stability_classes.groupby('mouse_id'):
    mouse_df = {}
    for col in is_pc[int(mouse_str.split("_")[0])].columns:
        if col <= 0:
            mouse_df[col] = mouse_data[mouse_data.period == 'pre']['classes'].iloc[0]
        elif col > 7:
            mouse_df[col] = mouse_data[mouse_data.period == 'late']['classes'].iloc[0]
        else:
            mouse_df[col] = mouse_data[mouse_data.period == 'early']['classes'].iloc[0]
    mouse_df = pd.DataFrame(mouse_df)
    stability_classes_neurons[int(mouse_str.split("_")[0])] = mouse_df.copy()

    rel_dates = np.array(mouse_df.columns)
    if 3 not in rel_dates:
        rel_dates[(rel_dates == 2) | (rel_dates == 4)] = 3
    rel_dates[(rel_dates == 5) | (rel_dates == 6) | (rel_dates == 7)] = 6
    rel_dates[(rel_dates == 8) | (rel_dates == 9) | (rel_dates == 10)] = 9
    rel_dates[(rel_dates == 11) | (rel_dates == 12) | (rel_dates == 13)] = 12
    rel_dates[(rel_dates == 14) | (rel_dates == 15) | (rel_dates == 16)] = 15
    rel_dates[(rel_dates == 17) | (rel_dates == 18) | (rel_dates == 19)] = 18
    rel_dates[(rel_dates == 20) | (rel_dates == 21) | (rel_dates == 22)] = 21
    rel_dates[(rel_dates == 23) | (rel_dates == 24) | (rel_dates == 25)] = 24
    if 28 not in rel_dates:
        rel_dates[(rel_dates == 26) | (rel_dates == 27) | (rel_dates == 28)] = 27

    # Uncomment this code if prestroke days should also be aligned (probably not good nor necessary)
    rel_sess = np.arange(len(rel_dates)) - np.argmax(np.where(rel_dates <= 0, rel_dates, -np.inf))
    rel_dates[(-5 < rel_sess) & (rel_sess < 1)] = np.arange(-np.sum((-5 < rel_sess) & (rel_sess < 1)) + 1, 1)
    mouse_df.columns = rel_dates
    stability_classes_neurons_aligned[int(mouse_str.split("_")[0])] = mouse_df

save_dict(stability_classes_neurons, 'neural_data\\stability_classes')
save_dict(stability_classes_neurons_aligned, 'neural_data\\stability_classes_aligned')


#%% UNMATCHED DATA

def array_to_series(arr: np.ndarray, name):
    series = pd.Series(dtype='object', name=name)
    for i in range(len(arr)):
        if np.all(np.isnan(arr[i])):
            series.at[i] = np.nan
        else:
            series.at[i] = arr[i]
    return series

session_strings = pd.read_csv(r'C:\Users\hheise.UZH\PycharmProjects\Caiman\custom scripts\preprint\Filippo\neural_data\session_strings.csv', index_col=0)
dff_normal = {}
dff_running = {}
decon_normal = {}
decon_running = {}
is_pc = {}
cell_coords = {}
spat_dff = {}
spat_decon = {}

behav = {}

for mouse in mice:
    print(mouse)
    microsphere_date = (common_mice.Surgery() & f'surgery_type="Microsphere injection"' &
                        f'mouse_id={mouse}').fetch1('surgery_date').date()

    restrictions = [{'mouse_id': mouse, **common_match.MatchedIndex().string2key(title=sess_str)}
                    for sess_str in session_strings[session_strings.mouse_id == mouse]['session']]

    sessions_dff_normal = []
    sessions_dff_run = []
    sessions_decon_normal = []
    sessions_decon_run = []
    sessions_pc = []
    sessions_com = []
    sessions_behav = []

    sessions_spat_dff = []
    sessions_spat_decon = []

    for sess_key in restrictions:

        raw_dff, mask_ids = (common_img.Segmentation & sess_key).get_traces('dff', include_id=True)
        raw_decon = (common_img.Segmentation & sess_key).get_traces('decon', decon_id=1)


        spat_dff_map = (hheise_placecell.BinnedActivity & sess_key & 'place_cell_id=2').get_trial_avg('dff')
        # spat_decon_map = (hheise_placecell.BinnedActivity & sess_key & 'place_cell_id=2').get_trial_avg('decon')

        rel_day = (datetime.strptime(sess_key['day'], '%Y-%m-%d').date() - microsphere_date).days


        # Only include normal trials
        trial_mask = (hheise_placecell.PCAnalysis & sess_key & 'place_cell_id=2').fetch1('trial_mask')
        norm_trials = (hheise_behav.VRSession & sess_key).get_normal_trials()
        norm_trial_mask = np.isin(trial_mask, norm_trials)
        dff_norm = raw_dff[:, norm_trial_mask]
        decon_norm = raw_decon[:, norm_trial_mask]

        # # Only include running frames
        # running_mask, aligned_frames = (hheise_placecell.Synchronization.VRTrial & sess_key & 'place_cell_id=2' &
        #                                 f'trial_id in {helper.in_query(norm_trials)}').fetch('running_mask', 'aligned_frames')
        # running_mask = np.concatenate(running_mask)
        # dff_run = dff_norm[:, running_mask]
        # decon_run = decon_norm[:, running_mask]

        # # Behavior data
        # arr = np.asarray(np.delete((hheise_behav.VRSession & sess_key).get_array(get_frame_avg=True), 4, axis=1), dtype=np.float16)
        #
        # # Add running mask to it
        # arr = np.hstack([arr, np.hstack(running_mask).T[..., np.newaxis]])
        #
        # ser = array_to_series(arr.T, name=rel_day).rename({0: 'trial_id', 1: 'timestamp', 2: 'position', 3: 'lick',
        #                                                    4: 'speed', 5: 'valve', 6: 'running_mask'})

        # Get place cell identity
        pc_masks = (hheise_placecell.PlaceCell.ROI & sess_key & 'place_cell_id=2' & 'is_place_cell=1'
                    & 'corridor_type=0').fetch('mask_id')
        is_pc_mask = np.zeros(len(mask_ids), dtype=int)
        is_pc_mask[np.isin(mask_ids, pc_masks)] = 1

        coms = (common_img.Segmentation.ROI & sess_key & 'accepted=1').fetch('com')

        sessions_dff_normal.append(array_to_series(dff_norm, name=rel_day))
        # sessions_dff_run.append(array_to_series(dff_run, name=rel_day))
        sessions_decon_normal.append(array_to_series(decon_norm, name=rel_day))
        # sessions_decon_run.append(array_to_series(decon_run, name=rel_day))
        sessions_pc.append(pd.Series(is_pc_mask, name=rel_day))
        sessions_com.append(pd.Series(coms, name=rel_day))

        # sessions_behav.append(ser)

        sessions_spat_dff.append(array_to_series(spat_dff_map, name=rel_day))
        # sessions_spat_decon.append(array_to_series(spat_decon_map, name=rel_day))

    dff_normal[mouse] = pd.DataFrame(sessions_dff_normal).T
    # dff_running[mouse] = pd.DataFrame(sessions_dff_run).T
    decon_normal[mouse] = pd.DataFrame(sessions_decon_normal).T
    # decon_running[mouse] = pd.DataFrame(sessions_decon_run).T
    is_pc[mouse] = pd.DataFrame(sessions_pc).T
    cell_coords[mouse] = pd.DataFrame(sessions_com).T

    # spat_decon[mouse] = pd.DataFrame(sessions_spat_decon).T
    spat_dff[mouse] = pd.DataFrame(sessions_spat_dff).T

del behav[112]
os.chdir(r'C:\Users\hheise.UZH\PycharmProjects\Caiman\custom scripts\preprint\Filippo')



os.chdir(r'C:\Users\hheise.UZH\PycharmProjects\Caiman\custom scripts\preprint\Filippo\neural_data')
save_dict(spat_dff, 'spatial_activity_maps_dff_all_cells')
save_dict(spat_decon, 'spatial_activity_maps_spikerate_all_cells')

save_dict(dff_normal, 'dff_all_cells')
save_dict(dff_running, 'dff_only_running')
save_dict(decon_normal, 'decon_all_cells')
save_dict(decon_running, 'decon_only_running')
save_dict(is_pc, 'is_pc_all_cells')
save_dict(cell_coords, 'cell_coords_all_cells')

folder = r'C:\Users\hheise.UZH\PycharmProjects\Caiman\custom scripts\preprint\Filippo\neural_data'
for filename in ['dff_all_cells_normal', 'dff_all_cells_only_running', 'decon_all_cells_normal', 'decon_all_cells_only_running']:

    with open(os.path.join(folder, f'{filename}.pkl'), 'rb') as file:
        old_data = pickle.load(file)

    os.chdir(r'C:\Users\hheise.UZH\PycharmProjects\Caiman\custom scripts\preprint\Filippo\neural_data')
    save_dict({k: v.applymap(lambda x: x.astype(np.float16) if type(x) == np.ndarray else x) for k, v in old_data.items()},
              f'{filename}')


# Filter existing data of matched cells for normal trials and running frames
with open(os.path.join(r'C:\Users\hheise.UZH\PycharmProjects\Caiman\custom scripts\preprint\Filippo\neural_data', 'dff.pkl'), 'rb') as file:
    old_dff = pickle.load(file)
with open(os.path.join(r'C:\Users\hheise.UZH\PycharmProjects\Caiman\custom scripts\preprint\Filippo\neural_data', 'decon.pkl'), 'rb') as file:
    old_decon = pickle.load(file)

dff_normal = {}
dff_running = {}
decon_normal = {}
decon_running = {}
for mouse in old_dff.keys():
    print(mouse)
    restrictions = [{'mouse_id': mouse, **common_match.MatchedIndex().string2key(title=sess_str)}
                    for sess_str in session_strings[session_strings.mouse_id == mouse]['session']]

    sessions_dff_normal = []
    sessions_dff_run = []
    sessions_decon_normal = []
    sessions_decon_run = []
    for col_idx, sess_key in enumerate(restrictions):

        rel_day = old_dff[mouse].columns[col_idx]

        curr_dff = old_dff[mouse].iloc[:, col_idx].copy()
        curr_decon = old_dff[mouse].iloc[:, col_idx].copy()
        nan_mask = curr_dff.isna()
        n_frames = len(curr_dff[~nan_mask].iloc[0])
        curr_dff.loc[nan_mask] = curr_dff.loc[nan_mask].apply(lambda x: np.ones(n_frames)*np.nan)
        curr_decon.loc[nan_mask] = curr_decon.loc[nan_mask].apply(lambda x: np.ones(n_frames)*np.nan)

        raw_dff = np.stack(curr_dff)
        raw_decon = np.stack(curr_decon)

        # Only include normal trials
        trial_mask = (hheise_placecell.PCAnalysis & sess_key & 'place_cell_id=2').fetch1('trial_mask')
        norm_trials = (hheise_behav.VRSession & sess_key).get_normal_trials()
        norm_trial_mask = np.isin(trial_mask, norm_trials)

        try:
            dff_norm = raw_dff[:, norm_trial_mask]
            decon_norm = raw_decon[:, norm_trial_mask]
        except IndexError:
            print(f'\tIndexError when masking normal trials at {sess_key}.\n\t\tUsing indices instead.')
            norm_trial_idx = np.where(norm_trial_mask)[0]
            dff_norm = raw_dff[:, norm_trial_idx]
            decon_norm = raw_decon[:, norm_trial_idx]


        # Only include running frames
        running_mask, aligned_frames = (hheise_placecell.Synchronization.VRTrial & sess_key & 'place_cell_id=2' &
                                        f'trial_id in {helper.in_query(norm_trials)}').fetch('running_mask', 'aligned_frames')
        running_mask = np.concatenate(running_mask)
        dff_run = dff_norm[:, running_mask]
        decon_run = decon_norm[:, running_mask]

        sessions_dff_normal.append(array_to_series(dff_norm, name=rel_day))
        sessions_dff_run.append(array_to_series(dff_run, name=rel_day))
        sessions_decon_normal.append(array_to_series(decon_norm, name=rel_day))
        sessions_decon_run.append(array_to_series(decon_run, name=rel_day))

    dff_normal[mouse] = pd.DataFrame(sessions_dff_normal).T
    dff_running[mouse] = pd.DataFrame(sessions_dff_run).T
    decon_normal[mouse] = pd.DataFrame(sessions_decon_normal).T
    decon_running[mouse] = pd.DataFrame(sessions_decon_run).T

# Transform array to float16 before saving to save disk space
os.chdir(r'C:\Users\hheise.UZH\PycharmProjects\Caiman\custom scripts\preprint\Filippo\neural_data')
save_dict({k: v.applymap(lambda x: x.astype(np.float16) if type(x) == np.ndarray else x) for k, v in dff_normal.items()},
          'dff_tracked_normal')
save_dict({k: v.applymap(lambda x: x.astype(np.float16) if type(x) == np.ndarray else x) for k, v in dff_running.items()},
          'dff_tracked_only_running')
save_dict({k: v.applymap(lambda x: x.astype(np.float16) if type(x) == np.ndarray else x) for k, v in decon_normal.items()},
          'decon_tracked_normal')
save_dict({k: v.applymap(lambda x: x.astype(np.float16) if type(x) == np.ndarray else x) for k, v in decon_running.items()},
          'decon_tracked_only_running')

#%% Load data for examination

with open(os.path.join(r'C:\Users\hheise.UZH\PycharmProjects\Caiman\custom scripts\preprint\Filippo\neural_data',
                       f'spatial_activity_maps_dff.pkl'), 'rb') as file:
    spat = pickle.load(file)
with open(os.path.join(r'C:\Users\hheise.UZH\PycharmProjects\Caiman\custom scripts\preprint\Filippo\neural_data',
                       f'stability_classes.pkl'), 'rb') as file:
    stab_classes = pickle.load(file)
with open(os.path.join(r'C:\Users\hheise.UZH\PycharmProjects\Caiman\custom scripts\preprint\Filippo\neural_data',
                       f'is_pc.pkl'), 'rb') as file:
    is_pc = pickle.load(file)

with open(os.path.join(r'C:\Users\hheise.UZH\PycharmProjects\Caiman\custom scripts\preprint\Filippo\neural_data',
                       f'is_pc_all_cells.pkl'), 'rb') as file:
    is_pc_all = pickle.load(file)

spat41 = spat[85]
stab41 = stab_classes[85]
pc41 = is_pc[85]

spat_mask = np.array(spat41.isna())
pc_mask = np.array(pc41.isna())
np.array_equal(spat_mask, pc_mask)
