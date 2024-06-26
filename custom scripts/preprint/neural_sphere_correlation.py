#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Created on 14/11/2023 17:48
@author: hheise

Correlate various neural metrics against sphere loads
"""
import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from scipy import stats
import statsmodels.api as sm

from util import helper
from schema import hheise_placecell, hheise_behav, hheise_hist, hheise_pvc, hheise_decoder, common_mice, common_img
from preprint import data_cleaning as dc


mice = [33, 41,  # Batch 3
        63, 69,  # Batch 5
        83, 85, 86, 89, 90, 91, 93, 94, 95,  # Batch 7
        108, 110, 111, 112, 113, 114, 115, 116, 122]  # Batch 8
exercise = [83, 85, 89, 90, 91] # Mice that received physical exercise training
single_days = [-4, -3, -2, -1, 0, 3, 6, 9, 12, 15, 18]  # days after 18 have few mice with many

def correlate_metric(df, y_metric, x_metric='spheres', time_name='rel_day_align', plotting=False, ax=None,
                     exclude_mice=None, include_mice=None, neg_corr=False, ci_level=0.95):

    if exclude_mice is not None and include_mice is not None:
        raise ValueError('Exclude_mice and include_mice cannot be defined simultaneously.')
    elif exclude_mice is not None:
        df_filt = df[~df.mouse_id.isin(exclude_mice)]
        print(df_filt.mouse_id.nunique(), 'mice used')
    elif include_mice is not None:
        df_filt = df[df.mouse_id.isin(include_mice)]
        print(df_filt.mouse_id.nunique(), 'mice used')
    else:
        df_filt = df

    n_mice = df_filt.mouse_id.nunique()

    corr = []
    for day, day_df in df_filt.groupby(time_name):

        if (time_name == 'rel_day_align') and (day in single_days) or (time_name != 'rel_day_align'):
        # if day_df.mouse_id.nunique() == n_mice:

            if time_name == 'phase':    # To compare phases, average phase metrics mouse-wise
                y = day_df.groupby('mouse_id')[y_metric].agg('mean')
                x = day_df.groupby('mouse_id')[x_metric].agg('mean')
            else:
                y = day_df[y_metric]
                x = day_df[x_metric]

            if y_metric in ['mae_quad', 'mae']:      # Invert metrics that are worse if large
                y = -y

            result = stats.pearsonr(x, y)
            ci = result.confidence_interval(ci_level)

            # Transform confidence interval to standard deviation following https://handbook-5-1.cochrane.org/chapter_7/7_7_3_2_obtaining_standard_deviations_from_standard_errors_and.htm
            # Get accurate t-value from scipy distribution (necessary for small samples with n < 60).
            # Might be misleading, since confidence interval was computed on Fisher-z-transformed values and thus are
            # not symmetric around the correlation coefficient.
            sd = np.sqrt(len(x)) * np.abs((ci.high - ci.low)) / (2*(stats.t.ppf(1-(1-ci_level)/2, len(x)-1)))

            corr.append(pd.DataFrame([dict(day=day, corr=result.statistic, corr_p=result.pvalue, y_metric=y_metric,
                                           ci_low=ci.low, ci_high=ci.high, sd=sd, x_metric=x_metric)]))

    corr = pd.concat(corr, ignore_index=True)

    if neg_corr:
        corr['corr'] = -corr['corr']

    if plotting:
        if ax is None:
            fig, ax = plt.subplots(1, 1)
        sns.lineplot(x=corr.day, y=corr['corr'], ax=ax)

    return corr


def iterative_exclusion(df: pd.DataFrame, y_metric, n_exclude, x_metric='spheres', time_name='rel_day_align', n_shuffle=None):

    mice_sorted = df[['mouse_id', 'spheres']].drop_duplicates().sort_values('spheres', ascending=False)

    true_df = []
    rng_df = []

    for n_ex in range(0, n_exclude+1):

        # Perform correlation with the n_ex most sphere-loaded mice removed
        corr_real = correlate_metric(df=df, y_metric=y_metric, x_metric=x_metric, time_name=time_name,
                                     exclude_mice=mice_sorted[:n_ex]['mouse_id'].to_numpy())
        corr_real['mice_excluded'] = [mice_sorted[:n_ex]['mouse_id'].to_numpy()] * len(corr_real)
        if n_ex == 0:
            corr_real['sphere_limit'] = 0
        else:
            corr_real['sphere_limit'] = mice_sorted.iloc[n_ex - 1]['spheres']
        corr_real['n_excluded'] = n_ex
        true_df.append(corr_real)

        # Control population with n_ex random mice removed
        if n_shuffle is None:
            n_shuffle = len(mice_sorted)
        for i in range(n_shuffle):
            ex_mice = np.random.choice(mice_sorted['mouse_id'], n_ex, replace=False)
            corr_shuff = correlate_metric(df=df, y_metric=y_metric, x_metric=x_metric, time_name=time_name,
                                          exclude_mice=ex_mice)
            corr_shuff['mice_excluded'] = [ex_mice] * len(corr_real)
            corr_shuff['n_excluded'] = n_ex
            if n_ex == 0:
                corr_shuff['sphere_limit'] = 0
            else:
                corr_shuff['sphere_limit'] = mice_sorted.iloc[n_ex - 1]['spheres']
            corr_shuff['n_shuffle'] = i
            rng_df.append(corr_shuff)

    true_df = pd.concat(true_df, ignore_index=True)
    rng_df = pd.concat(rng_df, ignore_index=True)

    true_df['label'] = true_df.apply(lambda x: f"{int(x['sphere_limit'])} ({x['n_excluded']})", axis=1)
    rng_df['label'] = rng_df.apply(lambda x: f"{int(x['sphere_limit'])} ({x['n_excluded']})", axis=1)

    return true_df, rng_df


def plot_simple_exclusion(df_true, df_shuff):

    fig, ax = plt.subplots(2, 2, layout='constrained', figsize=(18, 10), sharex='all', sharey='row')
    sns.lineplot(df_true, x='day', y='corr', hue='label', ax=ax[0, 0], palette='magma', marker="o")
    sns.lineplot(df_true, x='day', y='corr_p', hue='label', ax=ax[1, 0], palette='magma', marker="o")
    sns.lineplot(df_shuff, x='day', y='corr', hue='label', ax=ax[0, 1], palette='magma')
    sns.lineplot(df_shuff, x='day', y='corr_p', hue='label', ax=ax[1, 1], palette='magma')
    ax[1, 0].set(yscale='log')
    ax[1, 0].axhline(0.05, linestyle=':', color='black')
    ax[1, 0].axvline(0.5, linestyle='--', color='red')
    ax[1, 1].set(yscale='log')
    ax[1, 1].axhline(0.05, linestyle=':', color='black')
    ax[1, 1].axvline(0.5, linestyle='--', color='red')

    ax[0, 0].axvline(0.5, linestyle='--', color='red')
    ax[0, 0].axhline(0, linestyle=':', color='black')
    ax[0, 1].axvline(0.5, linestyle='--', color='red')
    ax[0, 1].axhline(0, linestyle=':', color='black')

def plot_exclusion_ci(df_true, df_shuff):

    n_splits = df_true.label.nunique()

    if df_true.y_metric.nunique() > 1:
        raise IndexError('Call function only for a single metric.')

    colors = sns.color_palette('magma', n_splits)
    fig, ax = plt.subplots(nrows=n_splits, ncols=1, sharex='all', sharey='all', figsize=(10, 12),  layout='constrained')

    for i, ((ex_true, split_df_true), (ex_rng, split_df_rng)) in enumerate(zip(df_true.groupby('n_excluded'), df_shuff.groupby('n_excluded'))):

        # Plot original trace with confidence intervals
        low = np.abs(split_df_true['corr'] - split_df_true['ci_low'])
        high = np.abs(split_df_true['corr'] - split_df_true['ci_high'])
        ax[i].errorbar(x=split_df_true['day'], y=split_df_true['corr'], yerr=np.stack((low, high)), color=colors[i],
                       capsize=4)

        # Plot average of all shuffled traces with average confidence intervals
        means = split_df_rng.groupby('day').agg({'corr': 'mean', 'ci_low': 'mean', 'ci_high': 'mean'}).reset_index()
        low = np.abs(means['corr'] - means['ci_low'])
        high = np.abs(means['corr'] - means['ci_high'])
        ax[i].errorbar(x=means['day'], y=means['corr'], yerr=np.stack((low, high)), color=colors[i],
                       capsize=4, linestyle='--')

        # Test whether CIs of true and shuffled data overlap
        diff_top = means['ci_high'].to_numpy() < split_df_true['ci_low'].to_numpy()
        diff_bot = means['ci_low'].to_numpy() > split_df_true['ci_high'].to_numpy()
        diff = diff_top | diff_bot

        # Paint background around points that are different
        x_span = means['day'].loc[diff]
        for x in x_span.items():
            # Borders are half-way until the previous/next datapoint
            if x[0] == 0:
                x0 = x[1]
            else:
                x0 = np.mean([means.day.iloc[x[0]-1], x[1]])
            if x[0] == len(means)-1:
                x1 = x[1]
            else:
                x1 = np.mean([means.day.iloc[x[0]+1], x[1]])
            ax[i].axvspan(xmin=x0, xmax=x1, color='red', alpha=0.5)

        # Formatting
        ax[i].axhline(0, linestyle=':', color='grey')
        ax[i].axvline(0.5, linestyle=':', color='red')
        ax[i].spines[['right', 'top']].set_visible(False)
        ax[i].set_title(f'Sphere limit: {split_df_true["sphere_limit"].iloc[0]:.0f} '
                        f'({split_df_true["n_excluded"].iloc[0]} excluded)')
        ax[i].set_ylabel('Pearson`s r')
    ax[-1].set_xlabel('Days after microsphere injection')


#%% Load basic data
spheres = pd.DataFrame((hheise_hist.MicrosphereSummary.Metric & 'metric_name="spheres"' & 'username="hheise"' &
                        f'mouse_id in {helper.in_query(mice)}').proj(spheres='count_extrap').fetch('mouse_id', 'spheres', as_dict=True))
injection = pd.DataFrame((common_mice.Surgery & 'username="hheise"' & f'mouse_id in {helper.in_query(mice)}' &
                          'surgery_type="Microsphere injection"').fetch('mouse_id', 'surgery_date',as_dict=True))
injection.surgery_date = injection.surgery_date.dt.date
vr_performance = pd.DataFrame((hheise_behav.VRPerformance & f'mouse_id in {helper.in_query(mice)}' &
                               'perf_param_id=0').fetch('mouse_id', 'day', 'si_binned_run', as_dict=True))

#%% Decoder
metrics = ['accuracy', 'mae_quad', 'sensitivity_rz']
decoder = pd.DataFrame((hheise_decoder.BayesianDecoderWithinSession() &
                        'bayesian_id=1').fetch('mouse_id', 'day', *metrics, as_dict=True))
decoder = dc.merge_dfs(df=decoder, sphere_df=spheres, inj_df=injection, vr_df=vr_performance)

# Plot scatter plots
data = decoder[decoder.rel_day_align.isin(single_days)]
data = data[~data.mouse_id.isin(exercise)]
g = sns.FacetGrid(data, col='rel_day_align', col_wrap=4)
g.map_dataframe(sns.scatterplot, x='spheres', y='mae_quad').set(xscale='log')

### DAY-WISE ###
decoder_corr = pd.concat([correlate_metric(df=decoder, y_metric=met) for met in metrics], ignore_index=True)
decoder_corr[decoder_corr.y_metric == 'mae_quad'].pivot(index='day', columns='y_metric', values='ci_high').to_clipboard(index=False, header=False)

### CORRELATE AGAINST BEHAVIOR ###
decoder_corr = pd.concat([correlate_metric(df=decoder, y_metric=met, x_metric='si_binned_run', neg_corr=False) for met in metrics], ignore_index=True)
decoder_corr[decoder_corr.y_metric == 'mae_quad'].pivot(index='day', columns='y_metric', values='corr').to_clipboard(index=False)

# Exclude high-sphere-load mice
corr_true, corr_shuffle = iterative_exclusion(df=decoder, n_exclude=10, y_metric='mae_quad', x_metric='spheres', n_shuffle=10)
corr_true.pivot(index='day', columns='sphere_limit', values='corr').to_clipboard()

plot_simple_exclusion(df_true=corr_true, df_shuff=corr_shuffle)
plot_exclusion_ci(df_true=corr_true, df_shuff=corr_shuffle)



# Exclude exercise mice
decoder_corr_ex = pd.concat([correlate_metric(decoder, met, exclude_mice=exercise) for met in metrics], ignore_index=True)
decoder_corr_ex[decoder_corr_ex.y_metric == 'mae_quad'].pivot(index='day', columns='y_metric', values='corr').to_clipboard()
decoder_corr_ex[decoder_corr_ex.y_metric == 'mae_quad'].pivot(index='day', columns='y_metric', values='corr').to_clipboard(index=False, header=False)

### Average metric within each phase (not too useful) ###
decoder_corr = pd.concat([correlate_metric(decoder, met, time_name='phase') for met in metrics], ignore_index=True)
decoder_corr.pivot(index='day', columns='y_metric', values='corr').to_clipboard()

# Exclude exercise mice
decoder_corr_ex = pd.concat([correlate_metric(decoder, met, time_name='phase', exclude_mice=exercise) for met in metrics], ignore_index=True)
decoder_corr_ex.pivot(index='day', columns='metric', values='corr_p').to_clipboard(index=False, header=False)


#%% VR Performance

performance = dc.merge_dfs(df=vr_performance, sphere_df=spheres, inj_df=injection)

g = sns.FacetGrid(performance[performance.rel_day_align.isin(single_days)], col='rel_day_align', col_wrap=4)
g.map_dataframe(sns.scatterplot, x='spheres', y='si_binned_run').set(xscale='log')

performance_corr = correlate_metric(performance, 'si_binned_run')
performance_corr.pivot(index='day', columns='y_metric', values='ci_high').to_clipboard(index=False, header=False)

performance_corr_ex = correlate_metric(performance, 'si_binned_run', exclude_mice=exercise)
performance_corr_ex.pivot(index='day', columns='y_metric', values='corr').to_clipboard(index=False, header=False)

corr_true, corr_shuffle = iterative_exclusion(df=performance, n_exclude=10, y_metric='si_binned_run', x_metric='spheres', n_shuffle=10)
corr_true.pivot(index='day', columns='sphere_limit', values='corr').to_clipboard()

plot_simple_exclusion(df_true=corr_true, df_shuff=corr_shuffle)
plot_exclusion_ci(df_true=corr_true, df_shuff=corr_shuffle)


#%% PVC
metrics = ['max_pvc', 'min_slope', 'pvc_rel_dif']
pvc = pd.DataFrame((hheise_pvc.PvcCrossSessionEval() * hheise_pvc.PvcCrossSession & 'locations="all"' &
                    'circular=0').fetch('mouse_id', 'phase', 'day', 'max_pvc', 'min_slope', 'pvc_rel_dif', as_dict=True))
pvc.rename(columns={'phase': 'phase_orig'}, inplace=True)
pvc = dc.merge_dfs(df=pvc, sphere_df=spheres, inj_df=injection, vr_df=vr_performance)

pvc_corr = pd.concat([correlate_metric(pvc, met, time_name='phase_orig') for met in metrics], ignore_index=True)
pvc_corr.pivot(index='day', columns='y_metric', values='corr_p').loc[['pre', 'pre_post', 'early', 'late']].to_clipboard()

#%% Place cell ratio
pcr = pd.DataFrame((hheise_placecell.PlaceCell() & 'corridor_type=0' &
                    'place_cell_id=2').fetch('mouse_id', 'day', 'place_cell_ratio', as_dict=True))
pcr = dc.merge_dfs(df=pcr, sphere_df=spheres, inj_df=injection, vr_df=vr_performance)

pcr_corr = correlate_metric(pcr, y_metric='place_cell_ratio')
pcr_corr.pivot(index='day', columns='y_metric', values='corr_p').to_clipboard()

pcr_corr = correlate_metric(pcr, y_metric='place_cell_ratio', x_metric='si_binned_run', neg_corr=True)
pcr_corr.pivot(index='day', columns='y_metric', values='corr_p').to_clipboard(index=False)

corr_true, corr_shuffle = iterative_exclusion(df=pcr, n_exclude=10, y_metric='place_cell_ratio', x_metric='spheres', n_shuffle=10)
plot_simple_exclusion(df_true=corr_true, df_shuff=corr_shuffle)
plot_exclusion_ci(df_true=corr_true, df_shuff=corr_shuffle)

#%% Within-session stability
# stab = pd.DataFrame((hheise_placecell.SpatialInformation.ROI() * hheise_placecell.PlaceCell.ROI() & 'corridor_type=0' &
#                     'place_cell_id=2' & 'is_place_cell=1').fetch('mouse_id', 'day', 'stability', as_dict=True))
stab = pd.DataFrame((hheise_placecell.SpatialInformation.ROI() & 'corridor_type=0' &
                    'place_cell_id=2').fetch('mouse_id', 'day', 'stability', as_dict=True))
transform_stab = True   # Whether to transform Fisher-transformed stability values back to correlation coefficients
if transform_stab:
    stab['stability'] = np.tanh(stab['stability'])

stab = stab.groupby(['mouse_id', 'day']).agg('mean').reset_index()
stab = dc.merge_dfs(df=stab, sphere_df=spheres, inj_df=injection, vr_df=vr_performance)

stab_corr = correlate_metric(stab, y_metric='stability')
stab_corr.pivot(index='day', columns='y_metric', values='corr_p').to_clipboard(index=True, header=True)

stab_corr = correlate_metric(stab, y_metric='stability', x_metric='si_binned_run', neg_corr=True)
stab_corr.pivot(index='day', columns='y_metric', values='corr_p').to_clipboard(index=False, header=True)


corr_true, corr_shuffle = iterative_exclusion(df=stab, n_exclude=10, y_metric='stability', x_metric='spheres', n_shuffle=10)
plot_simple_exclusion(df_true=corr_true, df_shuff=corr_shuffle)
plot_exclusion_ci(df_true=corr_true, df_shuff=corr_shuffle)


g = sns.FacetGrid(stab[stab.rel_day_align.isin(single_days)], col='rel_day_align', col_wrap=4)
g.map_dataframe(sns.scatterplot, x='spheres', y='stability').set(xscale='log')
g = sns.FacetGrid(stab[stab.rel_day_align.isin(single_days)], col='rel_day_align', col_wrap=4)
g.map_dataframe(sns.scatterplot, x='si_binned_run', y='stability')

#%% Firing rate
fr = pd.DataFrame((common_img.ActivityStatistics.ROI * common_img.Segmentation.ROI &
                   'accepted=1').fetch('mouse_id', 'day', 'rate_spikes', as_dict=True))
fr = fr.groupby(['mouse_id', 'day']).agg('mean').reset_index()
fr = dc.merge_dfs(df=fr, sphere_df=spheres, inj_df=injection, vr_df=vr_performance)

fr_corr = correlate_metric(fr, y_metric='rate_spikes')
fr_corr.pivot(index='day', columns='y_metric', values='corr').to_clipboard(index=False, header=True)

fr_corr = correlate_metric(fr, y_metric='rate_spikes', x_metric='si_binned_run', neg_corr=True)
fr_corr.pivot(index='day', columns='y_metric', values='corr_p').to_clipboard(index=False, header=True)

corr_true, corr_shuffle = iterative_exclusion(df=fr, n_exclude=10, y_metric='rate_spikes', x_metric='spheres', n_shuffle=10)
plot_simple_exclusion(df_true=corr_true, df_shuff=corr_shuffle)
plot_exclusion_ci(df_true=corr_true, df_shuff=corr_shuffle)


g = sns.FacetGrid(fr[fr.rel_day_align.isin(single_days)], col='rel_day_align', col_wrap=4)
g.map_dataframe(sns.scatterplot, x='spheres', y='rate_spikes').set(xscale='log')
g = sns.FacetGrid(fr[fr.rel_day_align.isin(single_days)], col='rel_day_align', col_wrap=4)
g.map_dataframe(sns.scatterplot, x='si_binned_run', y='rate_spikes')


#%% Performance - Metric - Correlation

# def perform_linear_regressions(df):
#     for phase, dataframe in df.groupby('phase'):
#
#         clean_frame = dataframe.dropna(axis=0)
#
#         vars = clean_frame.loc[:, ~clean_frame.columns.isin(['mouse_id', 'phase', 'si_binned_run'])]
#         perf = clean_frame['si_binned_run']
#
#         model = sm.OLS(perf, sm.add_constant(vars['accuracy'])).fit()
#
#         result = stats.pearsonr(perf, vars['accuracy'])
#         ci = result.confidence_interval(0.95)
#
#
#         # x = sm.add_constant(clean_frame.loc[:, ~clean_frame.columns.isin(['mouse_id', 'phase', 'si_binned_run'])])
#         # y = clean_frame['si_binned_run']
#         #
#         # model = sm.OLS(y, x).fit()
#         # print(model.summary())
#
# def test_two_corr_coef(r1, n1, r2, n2):
#
#     def z_transform(r):
#         return 0.5 * np.log((1+r)/(1-r))
#
#     # Z-transform correlation coefficients
#     z_r1 = z_transform(r1)
#     z_r2 = z_transform(r2)
#
#     # Standard error of the difference
#     se_z = np.sqrt((1/(n1-3)) + (1/(n2-3)))
#
#     # Z statistic
#     z = (z_r1 - z_r2)/se_z

def run_glm(df):

    for phase, dataframe in df.groupby('phase'):

            clean_frame = dataframe.dropna(axis=0)

            x = sm.add_constant(clean_frame.loc[:, ~clean_frame.columns.isin(['mouse_id', 'phase', 'si_binned_run'])])
            y = clean_frame['si_binned_run']

            results = sm.GLM(y, x, family=sm.families.Gaussian()).fit()
            print(results.summary())

            x_std = x.apply(lambda col: (col - col.mean())/col.std(), axis=0)
            x_std['const'] = x['const']
            y_std = (y - y.mean())/y.std()

            results_std = sm.OLS(y, x).fit()
            print(results_std.summary())



merge_cols = ['mouse_id', 'day', 'spheres', 'si_binned_run', 'surgery_date', 'rel_day', 'rel_day_align']
big_merge = pd.merge(decoder, pvc, on=merge_cols, how='outer', suffixes=(None, '_pvc'))
big_merge = pd.merge(big_merge, pcr, on=merge_cols, how='outer', suffixes=(None, '_pcr'))
big_merge = pd.merge(big_merge, stab, on=merge_cols, how='outer', suffixes=(None, '_stab'))
big_merge = pd.merge(big_merge, fr, on=merge_cols, how='outer', suffixes=(None, '_fr'))

big_merge['index'] = big_merge.apply(func=lambda x: f'{x.mouse_id}/{x.day}/{x.phase}', axis=1)

# metrics = ['accuracy', 'sensitivity_rz', 'min_slope', 'max_pvc', 'place_cell_ratio', 'stability', 'rate_spikes']
# big_merge.set_index('index')[['si_binned_run', *metrics]].to_clipboard()

### Further processing
# Exclude novel corridor dates and M94
big_merge = big_merge[big_merge.day < pd.to_datetime("2022-09-09").date()]
big_merge = big_merge[big_merge.mouse_id != 94]
# Fix nan phases
big_merge['phase'] = big_merge['phase'].fillna('pre')

# Compute mouse-phase average
avg_merge = big_merge.groupby(['mouse_id', 'phase']).agg({'accuracy': 'mean', 'sensitivity_rz': 'mean',
                                                          'si_binned_run': 'mean', 'min_slope': 'mean', 'max_pvc': 'mean',
                                                          'place_cell_ratio': 'mean', 'stability': 'mean', 'rate_spikes': 'mean',
                                                          }).reset_index()
avg_merge.pivot(index=['mouse_id', 'si_binned_run'], columns='phase', values='stability').loc[:, ['pre', 'early', 'late']].reset_index().to_clipboard(index=True)

avg_merge.pivot(index='mouse_id', columns='phase', values='si_binned_run').loc[:, ['pre', 'early', 'late']].reset_index().to_clipboard(index=False)

# Put metrics into GLM


